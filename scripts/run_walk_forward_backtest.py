#!/usr/bin/env python3
"""Run walk-forward backtests via QuantPlatformKit BacktestOrchestrator."""

from __future__ import annotations

import argparse
import copy
import json
import hashlib
import tempfile
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
DEFAULT_STORE_ROOT = Path("/tmp/cn_equity_wf_store")


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


def _baseline_param_set_id(profile: str, params: dict[str, Any], *, synthetic_days: int) -> str:
    identity = {
        "params": params,
        "synthetic_days": synthetic_days,
    }
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"{profile}_baseline_{fingerprint}"


def _build_runner(*, synthetic_days: int) -> CnProxyBacktestRunner:
    return CnProxyBacktestRunner(synthetic_days=synthetic_days)


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
    target_root = store_root or DEFAULT_STORE_ROOT
    target_root.mkdir(parents=True, exist_ok=True)
    baseline_params = copy.deepcopy(params)
    runner = _build_runner(synthetic_days=synthetic_days)
    baseline_raw = runner.run(
        profile,
        baseline_params,
        start_date=None,
        end_date=None,
    )
    with tempfile.TemporaryDirectory(prefix=f"{profile}_wf_", dir=target_root) as scratch_dir:
        scratch_store = PerformanceStore(local_root=Path(scratch_dir))
        scratch_orchestrator = BacktestOrchestrator(store=scratch_store)
        scratch_orchestrator.register_runner("cn_equity", runner)
        via_orch = scratch_orchestrator.run(
            profile,
            domain="cn_equity",
            params=copy.deepcopy(baseline_params),
            param_set_id=f"{profile}_full_compare",
            start_date=None,
            end_date=None,
        )
        wf_params = copy.deepcopy(baseline_params)
        wf_results = scratch_orchestrator.walk_forward(
            profile,
            domain="cn_equity",
            params=wf_params,
            windows=windows,
            param_set_id=f"{profile}_wf",
        )
    sharpe_delta = abs(float(via_orch.sharpe_ratio or 0.0) - float(baseline_raw.sharpe_ratio or 0.0))
    mdd_delta = abs(float(via_orch.max_drawdown or 0.0) - float(baseline_raw.max_drawdown or 0.0))
    within_tolerance = sharpe_delta <= compare_tolerance and mdd_delta <= compare_tolerance
    if not within_tolerance:
        raise RuntimeError(
            "baseline comparison failed: "
            f"sharpe_delta={sharpe_delta:.6f}, max_drawdown_delta={mdd_delta:.6f}, "
            f"tolerance={compare_tolerance:.6f}"
        )
    store = PerformanceStore(local_root=target_root)
    orchestrator = BacktestOrchestrator(store=store)
    baseline = orchestrator.persist_result(
        baseline_raw,
        strategy_profile=profile,
        domain="cn_equity",
        params=baseline_params,
        param_set_id=_baseline_param_set_id(
            profile,
            baseline_params,
            synthetic_days=synthetic_days,
        ),
    )

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
