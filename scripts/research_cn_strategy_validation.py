#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies import etf_rotation_core as rotation_core
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_DEFENSIVE_SYMBOLS,
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_UNIVERSE_SYMBOLS,
    build_target_weights,
)

StrategySignalFn = Callable[..., tuple[Mapping[str, float], Mapping[str, object]]]

OFFENSIVE_SYMBOLS = DEFAULT_UNIVERSE_SYMBOLS
DEFENSIVE_SYMBOLS = DEFAULT_DEFENSIVE_SYMBOLS
BENCHMARK_SYMBOL = rotation_core.DEFAULT_BENCHMARK_SYMBOL


@dataclass(frozen=True)
class ValidationConfig:
    start: str = "2021-01-01"
    end: str = "2026-06-27"
    initial_cash: float = 1_000_000.0


def _download_etf_history(config: ValidationConfig) -> pd.DataFrame:
    import akshare as ak

    symbols = tuple(dict.fromkeys([*OFFENSIVE_SYMBOLS, *DEFENSIVE_SYMBOLS, BENCHMARK_SYMBOL]))
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=config.start.replace("-", ""),
            end_date=config.end.replace("-", ""),
            adjust="qfq",
        )
        if frame.empty:
            raise ValueError(f"akshare returned no rows for ETF {symbol}")
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": symbol,
                    "close": float(getattr(item, "收盘")),
                }
            )
    output = pd.DataFrame(rows)
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _close_matrix(market_history: pd.DataFrame) -> pd.DataFrame:
    return rotation_core.build_close_matrix(
        market_history,
        universe_symbols=OFFENSIVE_SYMBOLS,
        extra_symbols=[*DEFENSIVE_SYMBOLS, BENCHMARK_SYMBOL],
    )


def _metrics_for_period(daily_returns: pd.Series, start: str | None, end: str | None) -> dict[str, float | int]:
    series = daily_returns
    if start:
        series = series.loc[pd.Timestamp(start) :]
    if end:
        series = series.loc[: pd.Timestamp(end)]
    series = series.dropna()
    if series.empty:
        return {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0, "annual_volatility": 0.0}
    equity = (1.0 + series).cumprod()
    years = len(series) / 252.0
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "days": int(len(series)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": annual_return,
        "max_drawdown": float(drawdown.min()),
        "annual_volatility": float(series.std(ddof=0) * math.sqrt(252)),
    }


def _signal_primary(history: Any, **kwargs: Any):
    kwargs.setdefault("min_history_days", DEFAULT_MIN_HISTORY_DAYS)
    return build_target_weights(history, **kwargs)


def _signal_benchmark_hold(_history: Any, **_kwargs: Any):
    return {BENCHMARK_SYMBOL: 1.0}, {"label": "benchmark_hold_510300"}


def _signal_equal_weight_offensive(history: Any, **_kwargs: Any):
    close = _close_matrix(history)
    if len(close) < DEFAULT_MIN_HISTORY_DAYS:
        return {}, {"label": "equal_weight_offensive", "reason": "insufficient_history"}
    weight = 1.0 / len(OFFENSIVE_SYMBOLS)
    return {symbol: weight for symbol in OFFENSIVE_SYMBOLS}, {"label": "equal_weight_offensive"}


def _signal_defensive_blend(_history: Any, **_kwargs: Any):
    weight = 1.0 / len(DEFENSIVE_SYMBOLS)
    return {symbol: weight for symbol in DEFENSIVE_SYMBOLS}, {"label": "defensive_blend"}


def _signal_naked_momentum(history: Any, **_kwargs: Any):
    return build_target_weights(
        history,
        min_history_days=DEFAULT_MIN_HISTORY_DAYS,
        benchmark_symbol=None,
        top_n=2,
        target_annual_volatility=None,
        max_pair_correlation=1.0,
    )


def _signal_no_risk_off(history: Any, **_kwargs: Any):
    close = _close_matrix(history)
    if len(close) < DEFAULT_MIN_HISTORY_DAYS:
        return {}, {"label": "no_risk_off", "reason": "insufficient_history"}
    returns = close.pct_change().fillna(0.0)
    momentum = close.pct_change(rotation_core.DEFAULT_MOMENTUM_WINDOW_DAYS)
    trend = close / close.rolling(rotation_core.DEFAULT_TREND_WINDOW_DAYS).mean() - 1.0
    volatility = returns.rolling(rotation_core.DEFAULT_VOLATILITY_WINDOW_DAYS).std(ddof=0) * math.sqrt(252)
    score = momentum / volatility.replace(0.0, pd.NA)
    rows: list[dict[str, object]] = []
    for symbol in OFFENSIVE_SYMBOLS:
        symbol_momentum = rotation_core._finite_float(momentum[symbol].iloc[-1])
        symbol_trend = rotation_core._finite_float(trend[symbol].iloc[-1])
        symbol_volatility = rotation_core._finite_float(volatility[symbol].iloc[-1])
        symbol_score = rotation_core._finite_float(score[symbol].iloc[-1], default=float("-inf"))
        eligible = (
            math.isfinite(symbol_momentum)
            and math.isfinite(symbol_trend)
            and math.isfinite(symbol_volatility)
            and symbol_momentum > 0.0
            and symbol_trend > 0.0
            and symbol_volatility > 0.0
        )
        rows.append(
            {
                "symbol": symbol,
                "score": symbol_score,
                "volatility": symbol_volatility,
                "eligible": eligible,
            }
        )
    ranked = sorted((row for row in rows if row["eligible"]), key=lambda row: float(row["score"]), reverse=True)[
        : rotation_core.DEFAULT_TOP_N
    ]
    weights, _realized = rotation_core._build_weights_from_ranked_rows(
        ranked,
        returns=returns,
        weighting_mode=rotation_core.DEFAULT_WEIGHTING_MODE,
        volatility_window_days=rotation_core.DEFAULT_VOLATILITY_WINDOW_DAYS,
        target_annual_volatility=rotation_core.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        max_gross_exposure=rotation_core.DEFAULT_MAX_GROSS_EXPOSURE,
    )
    return weights, {"label": "no_risk_off", "selected_symbols": tuple(weights)}


CANDIDATES: dict[str, tuple[str, StrategySignalFn]] = {
    "cn_index_etf_tactical_rotation": ("当前策略：动量+趋势+基准risk-off+逆波+相关性过滤", _signal_primary),
    "benchmark_510300": ("基准：沪深300 ETF 买入持有", _signal_benchmark_hold),
    "equal_weight_offensive": ("对照：进攻池等权再平衡", _signal_equal_weight_offensive),
    "defensive_blend": ("对照：货基+国债 ETF 等权", _signal_defensive_blend),
    "naked_momentum": ("对照：裸动量 top2，无 risk-off/波动率目标", _signal_naked_momentum),
    "no_risk_off": ("对照：完整因子但去掉基准 MA200 risk-off", _signal_no_risk_off),
}


def run_validation(config: ValidationConfig) -> dict[str, Any]:
    market_history = _download_etf_history(config)
    backtest_config = ProxyBacktestConfig(
        initial_cash=config.initial_cash,
        min_history_days=DEFAULT_MIN_HISTORY_DAYS,
    )
    periods = {
        "full": (None, None),
        "2022": ("2022-01-01", "2022-12-31"),
        "2023": ("2023-01-01", "2023-12-31"),
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026_ytd": ("2026-01-01", config.end),
        "trailing_1y": ("2025-06-27", config.end),
    }
    results: dict[str, Any] = {
        "config": asdict(config),
        "data": {
            "rows": int(len(market_history)),
            "start": market_history["date"].min().date().isoformat(),
            "end": market_history["date"].max().date().isoformat(),
            "symbols": sorted(market_history["symbol"].unique().tolist()),
        },
        "candidates": {},
    }
    for key, (description, signal_fn) in CANDIDATES.items():
        backtest = run_proxy_backtest(
            market_history,
            signal_fn,
            config=backtest_config,
            strategy_kwargs={"min_history_days": DEFAULT_MIN_HISTORY_DAYS},
        )
        results["candidates"][key] = {
            "description": description,
            "overall_metrics": backtest.metrics,
            "period_metrics": {
                period: _metrics_for_period(backtest.daily_returns, start, end) for period, (start, end) in periods.items()
            },
            "rebalance_count": len(backtest.rebalance_events),
            "final_equity": float(backtest.equity_curve.iloc[-1]),
        }
    primary = results["candidates"]["cn_index_etf_tactical_rotation"]["period_metrics"]["full"]
    benchmark = results["candidates"]["benchmark_510300"]["period_metrics"]["full"]
    results["summary"] = {
        "primary_beats_benchmark_full_period": primary["total_return"] > benchmark["total_return"],
        "primary_max_drawdown_vs_benchmark": {
            "primary": primary["max_drawdown"],
            "benchmark": benchmark["max_drawdown"],
        },
        "rank_by_full_total_return": sorted(
            results["candidates"].items(),
            key=lambda item: item[1]["period_metrics"]["full"]["total_return"],
            reverse=True,
        ),
    }
    return results


def _print_rank_table(payload: dict[str, Any]) -> None:
    print("\n=== A股 ETF 策略 proxy 回测对比（全样本 total_return）===\n")
    rows = payload["summary"]["rank_by_full_total_return"]
    for rank, (key, item) in enumerate(rows, start=1):
        full = item["period_metrics"]["full"]
        print(
            f"{rank}. {key}: total={full['total_return']:.2%} "
            f"ann={full['annual_return']:.2%} mdd={full['max_drawdown']:.2%} "
            f"| {item['description']}"
        )
    print("\n数据区间:", payload["data"]["start"], "~", payload["data"]["end"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CN ETF strategy candidates against mainstream baselines.")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--start", default=ValidationConfig.start)
    parser.add_argument("--end", default=ValidationConfig.end)
    args = parser.parse_args()
    payload = run_validation(ValidationConfig(start=args.start, end=args.end))
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.write_text(text + "\n")
    _print_rank_table(payload)
    print(text)


if __name__ == "__main__":
    main()
