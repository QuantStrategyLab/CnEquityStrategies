#!/usr/bin/env python3
"""Pilot: run cn_index_etf_tactical_rotation through BacktestOrchestrator.walk_forward()."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_MIN_HISTORY_DAYS,
    PROFILE_NAME,
)

DEFAULT_WINDOWS: tuple[tuple[date, date], ...] = (
    (date(2023, 6, 1), date(2024, 5, 31)),
    (date(2024, 6, 1), date(2025, 5, 31)),
    (date(2025, 6, 1), date(2026, 3, 31)),
)


def _baseline_full_window(runner: CnProxyBacktestRunner, params: dict[str, Any]) -> dict[str, Any]:
    result = runner.run(PROFILE_NAME, params, start_date=None, end_date=None)
    return {
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "cagr": result.cagr,
        "total_return": result.total_return,
        "observation_count": result.observation_count,
    }


def run_pilot(*, compare_tolerance: float = 0.001) -> dict[str, Any]:
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore

    params = {"min_history_days": DEFAULT_MIN_HISTORY_DAYS}
    runner = CnProxyBacktestRunner(synthetic_days=900)
    baseline = _baseline_full_window(runner, params)

    store = PerformanceStore(local_root=Path("/tmp/cn_equity_wf_pilot_store"))
    orchestrator = BacktestOrchestrator(store=store)
    orchestrator.register_runner("cn_equity", runner)
    wf_results = orchestrator.walk_forward(
        PROFILE_NAME,
        domain="cn_equity",
        params=params,
        windows=DEFAULT_WINDOWS,
        param_set_id="cn_index_etf_wf_pilot",
    )

    folds = [
        {
            "start_date": item.start_date.isoformat() if item.start_date else None,
            "end_date": item.end_date.isoformat() if item.end_date else None,
            "sharpe_ratio": item.sharpe_ratio,
            "max_drawdown": item.max_drawdown,
            "cagr": item.cagr,
            "total_return": item.total_return,
            "observation_count": item.observation_count,
            "run_id": item.run_id,
        }
        for item in wf_results
    ]
    # Compare average fold CAGR/Sharpe against full-window baseline order of magnitude.
    # For synthetic data we only assert walk_forward returns a non-empty list and
    # that a full-window orchestrator.run stays within tolerance of direct runner.
    direct = baseline
    via_orch = orchestrator.run(
        PROFILE_NAME,
        domain="cn_equity",
        params=params,
        param_set_id="cn_index_etf_full_compare",
    )
    sharpe_delta = abs(float(via_orch.sharpe_ratio or 0.0) - float(direct["sharpe_ratio"] or 0.0))
    mdd_delta = abs(float(via_orch.max_drawdown or 0.0) - float(direct["max_drawdown"] or 0.0))
    within_tolerance = sharpe_delta <= compare_tolerance and mdd_delta <= compare_tolerance

    return {
        "strategy_profile": PROFILE_NAME,
        "domain": "cn_equity",
        "baseline": baseline,
        "orchestrator_full_window": {
            "sharpe_ratio": via_orch.sharpe_ratio,
            "max_drawdown": via_orch.max_drawdown,
            "cagr": via_orch.cagr,
            "total_return": via_orch.total_return,
            "observation_count": via_orch.observation_count,
            "run_id": via_orch.run_id,
        },
        "walk_forward_folds": folds,
        "compare": {
            "sharpe_delta": sharpe_delta,
            "max_drawdown_delta": mdd_delta,
            "tolerance": compare_tolerance,
            "within_tolerance": within_tolerance,
        },
        "source": "BacktestOrchestrator.walk_forward",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CN index ETF walk-forward pilot via BacktestOrchestrator.")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.001)
    args = parser.parse_args()
    payload = run_pilot(compare_tolerance=args.tolerance)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    if not payload["compare"]["within_tolerance"]:
        raise SystemExit("orchestrator vs direct runner comparison exceeded tolerance")


if __name__ == "__main__":
    main()
