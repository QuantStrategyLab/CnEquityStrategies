#!/usr/bin/env python3
"""Pilot wrapper — delegates to run_walk_forward_backtest.py (task 3c)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_walk_forward_backtest import run_walk_forward  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CN index ETF walk-forward pilot (compat wrapper).")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.001)
    args = parser.parse_args()
    payload = run_walk_forward(
        profile="cn_index_etf_tactical_rotation",
        compare_tolerance=args.tolerance,
    )
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    return 0 if payload["compare"]["within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
