#!/usr/bin/env python3
"""Run walk-forward backtests via QuantPlatformKit BacktestOrchestrator."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner, SUPPORTED_PROFILES
from cn_equity_strategies.backtest.proxy_profile_registry import PROXY_PROFILE_REGISTRY

DEFAULT_WINDOWS: tuple[tuple[date, date], ...] = (
    (date(2023, 6, 1), date(2024, 5, 31)),
    (date(2024, 6, 1), date(2025, 5, 31)),
    (date(2025, 6, 1), date(2026, 3, 31)),
)


def _default_params(profile: str) -> dict[str, Any]:
    spec = PROXY_PROFILE_REGISTRY[profile]
    return {"min_history_days": spec.default_min_history_days}


def _result_payload(item: Any) -> dict[str, Any]:
    return {
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "sharpe_ratio": item.sharpe_ratio,
        "max_drawdown": item.max_drawdown,
        "cagr": item.cagr,
        "total_return": item.total_return,
        "observation_count": item.observation_count,
        "run_id": item.run_id,
    }


def run_walk_forward(
    *,
    profile: str,
    windows: tuple[tuple[date, date], ...] = DEFAULT_WINDOWS,
    synthetic_days: int = 900,
    compare_tolerance: float = 0.001,
    store_root: Path | None = None,
) -> dict[str, Any]:
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore

    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported profile={profile!r}; supported={sorted(SUPPORTED_PROFILES)}")

    params = _default_params(profile)
    runner = CnProxyBacktestRunner(synthetic_days=synthetic_days)
    baseline = runner.run(profile, params, start_date=None, end_date=None)

    store = PerformanceStore(local_root=store_root or Path("/tmp/cn_equity_wf_store"))
    orchestrator = BacktestOrchestrator(store=store)
    orchestrator.register_runner("cn_equity", runner)
    wf_results = orchestrator.walk_forward(
        profile,
        domain="cn_equity",
        params=params,
        windows=windows,
        param_set_id=f"{profile}_wf",
    )
    via_orch = orchestrator.run(
        profile,
        domain="cn_equity",
        params=params,
        param_set_id=f"{profile}_full_compare",
    )
    sharpe_delta = abs(float(via_orch.sharpe_ratio or 0.0) - float(baseline.sharpe_ratio or 0.0))
    mdd_delta = abs(float(via_orch.max_drawdown or 0.0) - float(baseline.max_drawdown or 0.0))
    within_tolerance = sharpe_delta <= compare_tolerance and mdd_delta <= compare_tolerance

    return {
        "strategy_profile": profile,
        "domain": "cn_equity",
        "baseline": _result_payload(baseline),
        "orchestrator_full_window": _result_payload(via_orch),
        "walk_forward_folds": [_result_payload(item) for item in wf_results],
        "compare": {
            "sharpe_delta": sharpe_delta,
            "max_drawdown_delta": mdd_delta,
            "tolerance": compare_tolerance,
            "within_tolerance": within_tolerance,
        },
        "source": "BacktestOrchestrator.walk_forward",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CN walk-forward backtest via BacktestOrchestrator.")
    parser.add_argument("--profile", default="cn_index_etf_tactical_rotation")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--synthetic-days", type=int, default=900)
    parser.add_argument("--tolerance", type=float, default=0.001)
    parser.add_argument("--store-root", type=Path)
    args = parser.parse_args()

    if args.list_profiles:
        print(json.dumps({"profiles": sorted(SUPPORTED_PROFILES)}, indent=2))
        return 0

    payload = run_walk_forward(
        profile=args.profile,
        synthetic_days=args.synthetic_days,
        compare_tolerance=args.tolerance,
        store_root=args.store_root,
    )
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    if not payload["compare"]["within_tolerance"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
