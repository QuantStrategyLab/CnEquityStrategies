#!/usr/bin/env python3
"""Generic CN proxy research backtest via BacktestOrchestrator adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC, ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.orchestrator_research import run_proxy_profile_backtest  # noqa: E402
from cn_equity_strategies.backtest.proxy_profile_registry import SUPPORTED_PROFILES  # noqa: E402
from scripts.run_walk_forward_backtest import run_walk_forward  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CN proxy strategy backtest via orchestrator adapters (task 3c)."
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--mode", choices=("single", "walk_forward"), default="single")
    parser.add_argument("--synthetic-days", type=int, default=900)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    if args.list_profiles:
        print(json.dumps({"profiles": sorted(SUPPORTED_PROFILES)}, indent=2))
        return 0

    if args.mode == "walk_forward":
        payload = run_walk_forward(profile=args.profile, synthetic_days=args.synthetic_days)
    else:
        payload = run_proxy_profile_backtest(args.profile, synthetic_days=args.synthetic_days)

    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
