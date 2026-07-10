#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.orchestrator_research import run_proxy_profile_backtest
from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_MIN_HISTORY_DAYS,
    PROFILE_NAME,
    build_target_weights,
)

DEFAULT_ETF_SYMBOLS = (
    "510300",
    "510500",
    "159915",
    "588000",
    "512100",
    "512170",
    "515030",
    "512760",
    "518880",
    "513100",
    "511880",
    "511260",
)


@dataclass(frozen=True)
class ResearchConfig:
    start: str = "2023-01-01"
    end: str = "2026-06-01"
    initial_cash: float = 1_000_000.0


def _signal_fn(history: Any, **kwargs: Any):
    return build_target_weights(history, **kwargs)


def _download_market_history(config: ResearchConfig) -> pd.DataFrame:
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - research helper only
        raise SystemExit(
            "akshare is required for live proxy backtest; install cn-equity-snapshot-pipelines[public-data] "
            "or run with --synthetic"
        ) from exc

    rows: list[dict[str, object]] = []
    for symbol in DEFAULT_ETF_SYMBOLS:
        frame = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=config.start.replace("-", ""),
            end_date=config.end.replace("-", ""),
            adjust="qfq",
        )
        if frame.empty:
            continue
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": symbol,
                    "close": float(getattr(item, "收盘")),
                }
            )
    output = pd.DataFrame(rows)
    if output.empty:
        raise ValueError("akshare returned no ETF history rows")
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def run(config: ResearchConfig, *, legacy: bool = False) -> dict[str, Any]:
    if not legacy:
        payload = run_proxy_profile_backtest(
            PROFILE_NAME,
            synthetic_days=500,
            params={"min_history_days": DEFAULT_MIN_HISTORY_DAYS},
        )
        return {
            "config": asdict(config),
            "synthetic": True,
            "orchestrator": True,
            "profile": PROFILE_NAME,
            "metrics": payload["metrics"],
            "source": payload["source"],
        }

    market_history = _download_market_history(config)
    backtest = run_proxy_backtest(
        market_history,
        _signal_fn,
        config=ProxyBacktestConfig(
            initial_cash=config.initial_cash,
            min_history_days=DEFAULT_MIN_HISTORY_DAYS,
        ),
        strategy_kwargs={"min_history_days": DEFAULT_MIN_HISTORY_DAYS},
    )
    return {
        "config": asdict(config),
        "synthetic": False,
        "data_rows": int(len(market_history)),
        "symbols": sorted(market_history["symbol"].unique().tolist()),
        "rebalance_count": len(backtest.rebalance_events),
        "metrics": backtest.metrics,
        "final_equity": float(backtest.equity_curve.iloc[-1]),
        "final_cash": backtest.final_cash,
        "final_holdings": backtest.final_holdings,
        "last_rebalance": backtest.rebalance_events[-1] if backtest.rebalance_events else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy backtest for cn_index_etf_tactical_rotation.")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--legacy", "--analysis", dest="legacy", action="store_true", help="Run the legacy AkShare proxy backtest path.")
    parser.add_argument("--synthetic", action="store_true", help="Kept for compatibility; default path already uses the orchestrator profile.")
    args = parser.parse_args()
    payload = run(ResearchConfig(), legacy=args.legacy)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
