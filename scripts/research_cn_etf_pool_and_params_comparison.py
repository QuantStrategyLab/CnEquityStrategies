#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies import etf_rotation_core as rc
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_DEFENSIVE_SYMBOLS,
    DEFAULT_MIN_HISTORY_DAYS,
    DEFAULT_UNIVERSE_SYMBOLS,
    build_target_weights,
)

# Base offensive pool (current production universe)
BASE_OFFENSIVE = DEFAULT_UNIVERSE_SYMBOLS

# Expanded pool: base + liquid theme ETFs with history back to ~2021
# Note: A-share market has no dedicated "storage/memory" theme ETF as of 2026-06.
EXPANDED_OFFENSIVE_EXTRA = (
    "159819",  # AI 人工智能 ETF 易方达
    "159995",  # 芯片 ETF
    "159994",  # 通信 ETF
    "159852",  # 软件 ETF
    "159792",  # 港股通互联网 ETF
)

EXPANDED_OFFENSIVE = tuple(dict.fromkeys([*BASE_OFFENSIVE, *EXPANDED_OFFENSIVE_EXTRA]))

DEFENSIVE = DEFAULT_DEFENSIVE_SYMBOLS
BENCHMARK = rc.DEFAULT_BENCHMARK_SYMBOL


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    universe: tuple[str, ...]
    top_n: int
    target_vol: float | None
    risk_off: bool


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("base_default", "基线池 top2 vol14% risk-off", BASE_OFFENSIVE, 2, 0.14, True),
    Scenario("base_tuned", "基线池 top5 vol25% risk-off", BASE_OFFENSIVE, 5, 0.25, True),
    Scenario("base_aggressive", "基线池 top5 vol20% 无risk-off", BASE_OFFENSIVE, 5, 0.20, False),
    Scenario("expanded_default", "扩池 top2 vol14% risk-off", EXPANDED_OFFENSIVE, 2, 0.14, True),
    Scenario("expanded_tuned", "扩池 top5 vol25% risk-off", EXPANDED_OFFENSIVE, 5, 0.25, True),
    Scenario("expanded_aggressive", "扩池 top5 vol20% 无risk-off", EXPANDED_OFFENSIVE, 5, 0.20, False),
    Scenario("base_equal_weight", "基线池等权", BASE_OFFENSIVE, 0, None, False),
    Scenario("expanded_equal_weight", "扩池等权", EXPANDED_OFFENSIVE, 0, None, False),
)


def _download_history(symbols: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    import akshare as ak

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
            raise ValueError(f"no history for {symbol}")
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


def _period_metrics(daily_returns: pd.Series, start: str, end: str) -> dict[str, float]:
    series = daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if series.empty:
        return {"total_return": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + series).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return {"total_return": float(equity.iloc[-1] - 1.0), "max_drawdown": float(drawdown.min())}


def _run_scenario(market_history: pd.DataFrame, scenario: Scenario) -> dict[str, Any]:
    config = ProxyBacktestConfig(min_history_days=DEFAULT_MIN_HISTORY_DAYS)

    if scenario.top_n == 0:

        def signal_fn(_history: Any, **_kwargs: Any):
            weight = 1.0 / len(scenario.universe)
            return {symbol: weight for symbol in scenario.universe}, {"label": scenario.key}

        strategy_kwargs: dict[str, Any] = {}
    else:
        benchmark_symbol = rc.DEFAULT_BENCHMARK_SYMBOL if scenario.risk_off else None

        def signal_fn(history: Any, **kwargs: Any):
            merged = {
                **kwargs,
                "universe_symbols": scenario.universe,
                "top_n": scenario.top_n,
                "target_annual_volatility": scenario.target_vol,
                "benchmark_symbol": benchmark_symbol,
            }
            return build_target_weights(history, **merged)

        strategy_kwargs = {
            "min_history_days": DEFAULT_MIN_HISTORY_DAYS,
            "universe_symbols": scenario.universe,
            "top_n": scenario.top_n,
            "target_annual_volatility": scenario.target_vol,
            "benchmark_symbol": benchmark_symbol,
        }

    backtest = run_proxy_backtest(
        market_history,
        signal_fn,
        config=config,
        strategy_kwargs=strategy_kwargs,
    )
    full = backtest.metrics
    periods = {
        "2022": _period_metrics(backtest.daily_returns, "2022-01-01", "2022-12-31"),
        "2023": _period_metrics(backtest.daily_returns, "2023-01-01", "2023-12-31"),
        "2024": _period_metrics(backtest.daily_returns, "2024-01-01", "2024-12-31"),
        "2025": _period_metrics(backtest.daily_returns, "2025-01-01", "2025-12-31"),
        "2026_ytd": _period_metrics(backtest.daily_returns, "2026-01-01", "2026-06-27"),
    }
    return {
        "key": scenario.key,
        "label": scenario.label,
        "universe_size": len(scenario.universe),
        "annual_return": full["annual_return"],
        "total_return": full["total_return"],
        "max_drawdown": full["max_drawdown"],
        "annual_volatility": full["annual_volatility"],
        "sharpe_ratio": full["sharpe_ratio"],
        "rebalance_count": len(backtest.rebalance_events),
        "periods": periods,
        "last_selection": backtest.rebalance_events[-1]["metadata"].get("selected_symbols") if backtest.rebalance_events else None,
    }


def run_comparison(*, start: str, end: str) -> dict[str, Any]:
    all_symbols = tuple(
        dict.fromkeys([*EXPANDED_OFFENSIVE, *DEFENSIVE, BENCHMARK]),
    )
    market_history = _download_history(all_symbols, start, end)
    data_start = market_history["date"].min().date().isoformat()
    data_end = market_history["date"].max().date().isoformat()

    results = [_run_scenario(market_history, scenario) for scenario in SCENARIOS]
    ranked = sorted(results, key=lambda item: item["annual_return"], reverse=True)
    within_budget = [item for item in results if item["max_drawdown"] >= -0.35]
    within_budget.sort(key=lambda item: item["annual_return"], reverse=True)

    return {
        "data": {
            "start": data_start,
            "end": data_end,
            "expanded_extra_symbols": list(EXPANDED_OFFENSIVE_EXTRA),
            "storage_etf_note": "A-share market has no dedicated storage/memory theme ETF in AkShare universe scan.",
        },
        "scenarios": results,
        "rank_by_annual_return": [(item["key"], item["annual_return"], item["max_drawdown"]) for item in ranked],
        "best_within_35pct_mdd": within_budget[0] if within_budget else None,
    }


def _print_table(payload: dict[str, Any]) -> None:
    print(f"\n数据区间: {payload['data']['start']} ~ {payload['data']['end']}")
    print(f"扩池新增: {', '.join(payload['data']['expanded_extra_symbols'])}")
    print(f"说明: {payload['data']['storage_etf_note']}\n")
    print("=== 全场景对比（按年化排序）===\n")
    rows = sorted(payload["scenarios"], key=lambda item: item["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        flag = "✓" if row["max_drawdown"] >= -0.35 else " "
        print(
            f"{index:2}. [{flag}] {row['label']:<28} "
            f"ann={row['annual_return']:6.2%} mdd={row['max_drawdown']:7.2%} "
            f"total={row['total_return']:7.2%} vol={row['annual_volatility']:.2%}"
        )
    print("\n=== 2024–2025 科技行情段（主题 ETF 能否受益）===\n")
    for row in rows:
        p24 = row["periods"]["2024"]["total_return"]
        p25 = row["periods"]["2025"]["total_return"]
        print(f"  {row['label']:<28} 2024={p24:+6.2%}  2025={p25:+6.2%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare base vs expanded ETF pool and parameter tunings.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run_comparison(start=args.start, end=args.end)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.write_text(text + "\n")
    _print_table(payload)


if __name__ == "__main__":
    main()
