#!/usr/bin/env python3
"""Pilot wrapper — delegates to run_walk_forward_backtest.py (task 3c)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_walk_forward_backtest import run_walk_forward  # noqa: E402


def run_bounded_research(args) -> dict:
    from dataclasses import asdict
    import pandas as pd
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore
    from cn_equity_strategies.backtest.index_etf_research_job import (
        PROFILE, FIXED_STRATEGY_PARAMS, PROXY_LIMITATIONS, make_index_etf_optimizer,
    )
    from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig

    payload = {
        "strategy_profile": PROFILE, "status": "parked", "learning_only": True,
        "promotion_eligible": False, "live_ready": False, "size_zero_required": True, "no_order": True,
        "input_provenance": "caller_supplied_unverified", "strict_backtest_gate": "unavailable",
        "fixed_strategy_params": FIXED_STRATEGY_PARAMS,
        "cost_model": asdict(ProxyBacktestConfig()), "limitations": list(PROXY_LIMITATIONS), "trials": [],
    }
    missing = [name for name in ("market_history", "development_start", "development_end", "store_root")
               if getattr(args, name, None) is None]
    if missing:
        return {**payload, "reason": "research_inputs_missing", "missing": missing}
    try:
        optimize = make_index_etf_optimizer(
            market_history=pd.read_csv(args.market_history, dtype={"symbol": str}),
            development_start=args.development_start, development_end=args.development_end,
            store=PerformanceStore(local_root=args.store_root), trial_records=payload["trials"],
        )
        proposal = optimize(
            SimpleNamespace(strategy_profile=PROFILE, domain="cn_equity"),
            SimpleNamespace(max_param_keys=4, max_search_iterations=12),
        )
    except (OSError, ValueError, TypeError, RuntimeError):
        # Do not copy paths, vendor responses or data values into job output.
        return {**payload, "reason": "research_input_or_backtest_failed"}
    return {
        **payload, "status": "learning_completed", "reason": "strict_promotion_evidence_missing",
        "development_window": {"start": args.development_start.isoformat(), "end": args.development_end.isoformat()},
        "proposal": proposal.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CN index ETF walk-forward pilot (compat wrapper).")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.001)
    parser.add_argument("--bounded-research", action="store_true", help="Run explicit-input development search.")
    parser.add_argument("--market-history", type=Path)
    parser.add_argument("--development-start", type=date.fromisoformat)
    parser.add_argument("--development-end", type=date.fromisoformat)
    parser.add_argument("--store-root", type=Path)
    args = parser.parse_args()
    if args.bounded_research:
        payload = run_bounded_research(args)
    else:
        payload = {
            **run_walk_forward(profile="cn_index_etf_tactical_rotation", compare_tolerance=args.tolerance),
            "input_provenance": "synthetic", "learning_only": True, "promotion_eligible": False,
            "live_ready": False, "size_zero_required": True, "no_order": True,
        }
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    if args.bounded_research:
        return 0 if payload["status"] == "learning_completed" else 2
    return 0 if payload["compare"]["within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
