#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as legacy_rotation
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_rotation
from cn_equity_strategies.strategies import industry_etf_rotation_core as industry_core

RebalanceFrequency = Literal["monthly", "biweekly"]
SentimentMode = Literal["off", "flow", "flow_crowding"]

VALIDATION_PERIODS: dict[str, tuple[str | None, str | None]] = {
    "full": (None, None),
    "bear_2021_2022": ("2021-01-01", "2022-12-31"),
    "recovery_2023": ("2023-01-01", "2023-12-31"),
    "theme_2024_2025": ("2024-01-01", "2025-12-31"),
    "train_2021_2023": ("2021-01-01", "2023-12-31"),
    "oos_2024_2026": ("2024-01-01", "2026-06-27"),
    "2022": ("2022-01-01", "2022-12-31"),
    "2023": ("2023-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_ytd": ("2026-01-01", "2026-06-27"),
}


@dataclass(frozen=True)
class Variant:
    key: str
    label: str
    profile: Literal["industry", "legacy", "benchmark"]
    sentiment_mode: SentimentMode = "flow_crowding"
    rebalance_frequency: RebalanceFrequency = "monthly"
    enable_benchmark_risk_off: bool = False


VARIANTS: tuple[Variant, ...] = (
    Variant("industry_full_monthly", "行业轮动+情绪+拥挤惩罚/月频", "industry", "flow_crowding", "monthly"),
    Variant("industry_momentum_monthly", "行业轮动纯动量/月频", "industry", "off", "monthly"),
    Variant("industry_sentiment_monthly", "行业轮动+成交额情绪/月频", "industry", "flow", "monthly"),
    Variant("industry_full_biweekly", "行业轮动+情绪+拥挤惩罚/双周频", "industry", "flow_crowding", "biweekly"),
    Variant("industry_riskoff_monthly", "行业轮动+情绪/月频+MA200防御", "industry", "flow_crowding", "monthly", True),
    Variant("legacy_global_monthly", "旧版全球ETF扩池/月频", "legacy", "off", "monthly"),
    Variant("benchmark_510300", "510300 买入持有", "benchmark", "off", "monthly"),
)


def _download_market_history(*, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    symbols = tuple(
        dict.fromkeys(
            [
                *industry_core.DEFAULT_UNIVERSE_SYMBOLS,
                *industry_core.DEFAULT_DEFENSIVE_SYMBOLS,
                industry_core.DEFAULT_BENCHMARK_SYMBOL,
                *legacy_rotation.DEFAULT_UNIVERSE_SYMBOLS,
                "518880",
                "513100",
            ]
        )
    )
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if frame.empty:
            raise ValueError(f"no ETF history for {symbol}")
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": symbol,
                    "close": float(getattr(item, "收盘")),
                    "volume": float(getattr(item, "成交额")),
                }
            )
    output = pd.DataFrame(rows)
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _period_metrics(daily_returns: pd.Series, start: str | None, end: str | None) -> dict[str, float | int]:
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


def _run_variant(market_history: pd.DataFrame, variant: Variant) -> dict[str, Any]:
    config = ProxyBacktestConfig(
        min_history_days=industry_rotation.DEFAULT_MIN_HISTORY_DAYS,
        rebalance_frequency=variant.rebalance_frequency,
    )

    if variant.profile == "benchmark":

        def signal_fn(_history: Any, **_kwargs: Any):
            return {industry_core.DEFAULT_BENCHMARK_SYMBOL: 1.0}, {"label": variant.key}

        strategy_kwargs: dict[str, Any] = {}
    elif variant.profile == "legacy":

        def signal_fn(history: Any, **kwargs: Any):
            merged = {
                **kwargs,
                "top_n": 5,
                "target_annual_volatility": 0.20,
                "benchmark_symbol": None,
            }
            return legacy_rotation.build_target_weights(history, **merged)

        strategy_kwargs = {
            "min_history_days": legacy_rotation.DEFAULT_MIN_HISTORY_DAYS,
            "top_n": 5,
            "target_annual_volatility": 0.20,
            "benchmark_symbol": None,
        }
    else:

        def signal_fn(history: Any, **kwargs: Any):
            merged = {
                **kwargs,
                "sentiment_mode": variant.sentiment_mode,
                "enable_benchmark_risk_off": variant.enable_benchmark_risk_off,
            }
            return industry_rotation.build_target_weights(history, **merged)

        strategy_kwargs = {
            "min_history_days": industry_rotation.DEFAULT_MIN_HISTORY_DAYS,
            "sentiment_mode": variant.sentiment_mode,
            "enable_benchmark_risk_off": variant.enable_benchmark_risk_off,
        }

    backtest = run_proxy_backtest(
        market_history,
        signal_fn,
        config=config,
        strategy_kwargs=strategy_kwargs,
    )
    period_metrics = {
        period: _period_metrics(backtest.daily_returns, start, end)
        for period, (start, end) in VALIDATION_PERIODS.items()
    }
    return {
        "key": variant.key,
        "label": variant.label,
        "profile": variant.profile,
        "sentiment_mode": variant.sentiment_mode,
        "rebalance_frequency": variant.rebalance_frequency,
        "enable_benchmark_risk_off": variant.enable_benchmark_risk_off,
        "overall": backtest.metrics,
        "period_metrics": period_metrics,
        "rebalance_count": len(backtest.rebalance_events),
        "final_equity": float(backtest.equity_curve.iloc[-1]),
    }


def run_validation(*, start: str, end: str) -> dict[str, Any]:
    market_history = _download_market_history(start=start, end=end)
    results = [_run_variant(market_history, variant) for variant in VARIANTS]
    ranked = sorted(results, key=lambda item: item["overall"]["annual_return"], reverse=True)
    within_budget = [item for item in results if item["overall"]["max_drawdown"] >= -0.35]
    within_budget.sort(key=lambda item: item["overall"]["annual_return"], reverse=True)
    industry_variants = [item for item in results if item["profile"] == "industry"]
    best_industry = max(industry_variants, key=lambda item: item["overall"]["annual_return"])
    legacy = next(item for item in results if item["key"] == "legacy_global_monthly")
    benchmark = next(item for item in results if item["key"] == "benchmark_510300")
    return {
        "design_notes": {
            "research_sources": [
                "CITIC/Guojin/Kaiyuan multi-factor industry rotation (momentum + flow + crowding)",
                "CMS industry momentum with crowding penalty",
                "A-share retail turnover supports sentiment proxy via ETF amount surge",
            ],
            "universe": list(industry_core.DEFAULT_UNIVERSE_SYMBOLS),
            "excluded_from_offensive_pool": ["513100", "518880"],
            "storage_theme_etf": "not available in AkShare scan",
        },
        "data": {
            "start": market_history["date"].min().date().isoformat(),
            "end": market_history["date"].max().date().isoformat(),
            "rows": int(len(market_history)),
        },
        "variants": results,
        "summary": {
            "best_overall": ranked[0]["key"],
            "best_within_35pct_mdd": within_budget[0]["key"] if within_budget else None,
            "best_industry_variant": best_industry["key"],
            "industry_beats_legacy_full_sample": best_industry["overall"]["total_return"]
            > legacy["overall"]["total_return"],
            "industry_beats_benchmark_full_sample": best_industry["overall"]["total_return"]
            > benchmark["overall"]["total_return"],
        },
    }


def _print_report(payload: dict[str, Any]) -> None:
    print("\n=== A股行业 ETF 轮动 — 多周期验证 ===\n")
    print(f"数据: {payload['data']['start']} ~ {payload['data']['end']}")
    print("行业池:", ", ".join(payload["design_notes"]["universe"]))
    print()
    rows = sorted(payload["variants"], key=lambda item: item["overall"]["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        flag = "✓" if overall["max_drawdown"] >= -0.35 else " "
        print(
            f"{index:2}. [{flag}] {row['label']:<34} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print("\n=== 分周期（total_return）: 行业完整版 vs 旧全球版 vs 510300 ===\n")
    keys = ("industry_full_monthly", "legacy_global_monthly", "benchmark_510300")
    by_key = {item["key"]: item for item in payload["variants"]}
    header = f"{'period':<16}" + "".join(f"{key:>22}" for key in keys)
    print(header)
    for period in ("bear_2021_2022", "recovery_2023", "theme_2024_2025", "train_2021_2023", "oos_2024_2026"):
        line = f"{period:<16}"
        for key in keys:
            metric = by_key[key]["period_metrics"][period]
            line += f"{metric['total_return']:>22.2%}"
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CN industry ETF rotation across cycles and variants.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run_validation(start=args.start, end=args.end)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.write_text(text + "\n")
    _print_report(payload)


if __name__ == "__main__":
    main()
