#!/usr/bin/env python3
"""Proxy backtest for cn_chinext_tactical_rotation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC,):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    compute_backtest_metrics,
    run_proxy_backtest,
)
from cn_equity_strategies.strategies import cn_chinext_tactical_rotation as tactical  # noqa: E402


def _download_market_history(start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    def _prefix(symbol: str) -> str:
        return "sz" if symbol.startswith("159") else "sh"

    rows: list[dict[str, object]] = []
    for symbol in ("159915", "159949", "511880", "511260", "510300"):
        frame = ak.stock_zh_a_hist_tx(
            symbol=_prefix(symbol) + symbol,
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "date"),
                    "symbol": symbol,
                    "close": float(getattr(item, "close")),
                }
            )
    output = pd.DataFrame(rows)
    if output.empty:
        raise ValueError("akshare returned no ETF history rows")
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _metrics_slice(daily_returns: pd.Series, start: str, end: str) -> dict[str, float | int]:
    series = daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if series.empty:
        return {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + series).cumprod()
    years = len(series) / 252.0
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "days": int(len(series)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": annual_return,
        "max_drawdown": float(drawdown.min()),
    }


def run(*, start: str, end: str, target_vol: float = 0.50) -> dict[str, Any]:
    market_history = _download_market_history(start, end)

    def signal_fn(history: Any, **_kwargs: Any):
        signal = tactical.compute_latest_signal(
            history,
            target_annual_volatility=target_vol,
            min_history_days=tactical.DEFAULT_MIN_HISTORY_DAYS,
        )
        return signal["weights"], signal

    backtest = run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(min_history_days=tactical.DEFAULT_MIN_HISTORY_DAYS),
        strategy_kwargs={},
    )
    benchmark = run_proxy_backtest(
        market_history.loc[market_history["symbol"] == "510300"].copy(),
        lambda _h, **_k: ({"510300": 1.0}, {"label": "510300"}),
        config=ProxyBacktestConfig(min_history_days=tactical.DEFAULT_MIN_HISTORY_DAYS),
        universe_symbols=("510300",),
    )
    full = backtest.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    benchmark_returns = benchmark.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    return {
        "start": start,
        "end": end,
        "profile": tactical.PROFILE_NAME,
        "target_annual_volatility": target_vol,
        "full_sample": compute_backtest_metrics(full),
        "benchmark": compute_backtest_metrics(benchmark_returns),
        "periods": {
            "2021_2022": {
                "strategy": _metrics_slice(backtest.daily_returns, "2021-01-01", "2022-12-31"),
                "benchmark": _metrics_slice(benchmark.daily_returns, "2021-01-01", "2022-12-31"),
            },
            "2023_2026": {
                "strategy": _metrics_slice(backtest.daily_returns, "2023-01-01", end),
                "benchmark": _metrics_slice(benchmark.daily_returns, "2023-01-01", end),
            },
            "2024_2026": {
                "strategy": _metrics_slice(backtest.daily_returns, "2024-01-01", end),
                "benchmark": _metrics_slice(benchmark.daily_returns, "2024-01-01", end),
            },
        },
        "benchmark_note": "benchmark is 510300 history only; this script is focused on strategy validation",
        "data_rows": int(len(market_history)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy backtest for cn_chinext_tactical_rotation.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--target-vol", type=float, default=0.50)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run(start=args.start, end=args.end, target_vol=float(args.target_vol))
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
