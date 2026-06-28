#!/usr/bin/env python3
"""Phase 3: vol25 MA120 PIT universe vs baseline + single-name weight cap sweep."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for candidate in (SRC, SCRIPTS):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    CONSERVATIVE_V1_PRESET,
    CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS,
    STOCK_MOMENTUM_RETURN_FOCUSED_GATE,
)
from research_cn_industry_etf_rotation_aggressive_matrix import _run_preset  # noqa: E402
from research_cn_industry_etf_rotation_validation import _download_market_history  # noqa: E402
from research_cn_ma120_vol_and_combo_scan import DEFAULT_END, DEFAULT_START, MDD_BUDGET  # noqa: E402
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset,
)

DEFAULT_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "key": "vol25_baseline",
        "label": "vol25 MA120 — latest CSI500 table",
        "preset_overrides": {"universe_mode": "csi500"},
    },
    {
        "key": "vol25_csi500_pit",
        "label": "vol25 MA120 — inclusion-date PIT filter",
        "preset_overrides": {"universe_mode": "csi500_pit"},
    },
    {
        "key": "vol25_cap10",
        "label": "vol25 MA120 — max single-name weight 10%",
        "preset_overrides": {"universe_mode": "csi500", "max_single_name_weight": 0.10},
    },
    {
        "key": "vol25_cap08",
        "label": "vol25 MA120 — max single-name weight 8%",
        "preset_overrides": {"universe_mode": "csi500", "max_single_name_weight": 0.08},
    },
    {
        "key": "vol25_pit_cap10",
        "label": "vol25 MA120 — PIT + 10% cap",
        "preset_overrides": {
            "universe_mode": "csi500_pit",
            "max_single_name_weight": 0.10,
        },
    },
)


def _run_vol25_variant(
    *,
    start: str,
    end: str,
    key: str,
    label: str,
    preset_overrides: dict[str, Any],
) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    base_preset = deepcopy(STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS[CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY])
    base_preset.update(preset_overrides)
    stock_history, candidate_universe, active = _load_universe_bundle(
        base_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )
    runtime = _materialize_preset(base_preset, stock_universe=active)
    result = _run_preset(stock_history, key, runtime)
    return {
        "key": key,
        "label": label,
        "preset_overrides": preset_overrides,
        "universe": {
            "candidate_count": len(candidate_universe),
            "active_count": len(active),
            "universe_mode": base_preset.get("universe_mode"),
            "pit_index_code": runtime.get("pit_index_code"),
            "max_single_name_weight": runtime.get("max_single_name_weight"),
        },
        "overall": result["overall"],
        "period_metrics": result["period_metrics"],
        "oos_2024_2026": result["period_metrics"]["oos_2024_2026"],
        "bear_2021_2022": result["period_metrics"]["bear_2021_2022"],
        "within_mdd_budget": float(result["overall"]["max_drawdown"]) >= MDD_BUDGET,
        "_gate_result": result,
    }


def run_phase3_comparison(*, start: str, end: str) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    etf_history = _download_market_history(start=download_start, end=end)
    conservative = _run_preset(etf_history, "conservative_v1", CONSERVATIVE_V1_PRESET)

    gate_candidates: dict[str, dict[str, Any]] = {"conservative_v1": conservative}
    variants: dict[str, dict[str, Any]] = {}
    for spec in DEFAULT_VARIANTS:
        payload = _run_vol25_variant(
            start=start,
            end=end,
            key=str(spec["key"]),
            label=str(spec["label"]),
            preset_overrides=dict(spec["preset_overrides"]),
        )
        gate_candidates[str(spec["key"])] = payload.pop("_gate_result")
        variants[str(spec["key"])] = payload

    baseline = variants["vol25_baseline"]["overall"]
    pit = variants["vol25_csi500_pit"]["overall"]
    gate_review = evaluate_promotion(
        gate_candidates,
        STOCK_MOMENTUM_RETURN_FOCUSED_GATE,
        baseline_key="conservative_v1",
    )

    return {
        "start": start,
        "end": end,
        "mdd_budget": MDD_BUDGET,
        "base_preset": CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
        "variants": variants,
        "delta_vs_baseline_non_pit": {
            "annual_return_pp": float(pit["annual_return"]) - float(baseline["annual_return"]),
            "max_drawdown_pp": float(pit["max_drawdown"]) - float(baseline["max_drawdown"]),
            "oos_total_return_pp": float(variants["vol25_csi500_pit"]["oos_2024_2026"]["total_return"])
            - float(variants["vol25_baseline"]["oos_2024_2026"]["total_return"]),
        },
        "return_focused_gate_vs_conservative": gate_review,
        "limitations": [
            "PIT filter uses current index members + inclusion dates, with price-history grandfathering for stale inclusion dates",
            "Removed historical members are not restored; full PIT requires CnEquitySnapshotPipelines membership snapshots",
            "Weight cap clips per-name weights before vol targeting; excess becomes implicit cash",
            "Research proxy — not unified multi-asset account simulation",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    print("\n=== Phase 3: vol25 PIT + weight cap ===\n")
    print(f"区间: {payload['start']} ~ {payload['end']}")
    for key, row in payload["variants"].items():
        overall = row["overall"]
        flag = "✓" if row["within_mdd_budget"] else "✗"
        print(
            f"  [{flag}] {key:<18} ann={overall['annual_return']:6.2%} "
            f"mdd={overall['max_drawdown']:7.2%} oos={row['oos_2024_2026']['total_return']:+7.2%}"
        )
    delta = payload["delta_vs_baseline_non_pit"]
    print(
        f"\nPIT vs non-PIT: ann {delta['annual_return_pp']:+.2%} | "
        f"mdd {delta['max_drawdown_pp']:+.2%} | "
        f"oos {delta['oos_total_return_pp']:+.2%}"
    )
    promoted = [item["key"] for item in payload["return_focused_gate_vs_conservative"].get("promoted") or []]
    print(f"\nReturn-focused gate promoted: {', '.join(promoted) or '(none)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MA120 Phase 3 PIT + weight cap comparison.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run_phase3_comparison(start=args.start, end=args.end)
    _print_report(payload)
    if args.json_output:
        serializable = json.loads(json.dumps(payload, default=str))
        args.json_output.write_text(json.dumps(serializable, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
