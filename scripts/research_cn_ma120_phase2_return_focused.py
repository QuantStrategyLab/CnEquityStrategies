#!/usr/bin/env python3
"""Phase 2: MA120 return-focused promotion gate + aggressive ETF weight grid."""

from __future__ import annotations

import argparse
import json
import sys
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
    AGGRESSIVE_V1_PRESET,
    CONSERVATIVE_V1_PRESET,
    CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS,
    STOCK_MOMENTUM_PROMOTION_GATE,
    STOCK_MOMENTUM_RETURN_FOCUSED_GATE,
)
from research_cn_industry_etf_rotation_aggressive_matrix import _run_preset  # noqa: E402
from research_cn_industry_etf_rotation_validation import _download_market_history  # noqa: E402
from research_cn_ma120_vol_and_combo_scan import (  # noqa: E402
    DEFAULT_END,
    DEFAULT_START,
    MDD_BUDGET,
    run_combo_weight_grid,
)
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset,
)

DEFAULT_ETF_WEIGHTS = (0.0, 0.30, 0.50, 0.70, 1.0)


def _run_ma120_variant_results(*, start: str, end: str) -> dict[str, dict[str, Any]]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    base_preset = next(iter(STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.values()))
    stock_history, _, active = _load_universe_bundle(
        base_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )
    results: dict[str, dict[str, Any]] = {}
    for key, preset in STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.items():
        runtime = _materialize_preset(preset, stock_universe=active)
        results[key] = _run_preset(stock_history, key, runtime)
    return results


def run_promotion_reviews(*, start: str, end: str) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    etf_history = _download_market_history(start=download_start, end=end)
    conservative = _run_preset(etf_history, "conservative_v1", CONSERVATIVE_V1_PRESET)
    aggressive = _run_preset(etf_history, "aggressive_v1", AGGRESSIVE_V1_PRESET)
    ma120_variants = _run_ma120_variant_results(start=start, end=end)

    def _review(baseline_key: str, gate: dict[str, Any]) -> dict[str, Any]:
        baseline = conservative if baseline_key == "conservative_v1" else aggressive
        payload = {baseline_key: baseline, **ma120_variants}
        return evaluate_promotion(payload, gate, baseline_key=baseline_key)

    return {
        "start": start,
        "end": end,
        "etf_baselines": {
            "conservative_v1": {
                "overall": conservative["overall"],
                "oos_2024_2026": conservative["period_metrics"]["oos_2024_2026"],
            },
            "aggressive_v1": {
                "overall": aggressive["overall"],
                "oos_2024_2026": aggressive["period_metrics"]["oos_2024_2026"],
            },
        },
        "ma120_variant_count": len(ma120_variants),
        "vs_conservative_standard_gate": _review("conservative_v1", STOCK_MOMENTUM_PROMOTION_GATE),
        "vs_conservative_return_focused_gate": _review(
            "conservative_v1",
            STOCK_MOMENTUM_RETURN_FOCUSED_GATE,
        ),
        "vs_aggressive_return_focused_gate": _review(
            "aggressive_v1",
            STOCK_MOMENTUM_RETURN_FOCUSED_GATE,
        ),
    }


def _print_promotion_report(payload: dict[str, Any]) -> None:
    print("\n=== P2.1 MA120 promotion gate 评估 ===\n")
    baselines = payload["etf_baselines"]
    print(
        f"ETF conservative: ann≈{baselines['conservative_v1']['overall']['annual_return']:.2%} "
        f"oos={baselines['conservative_v1']['oos_2024_2026']['total_return']:+.2%}"
    )
    print(
        f"ETF aggressive:   ann≈{baselines['aggressive_v1']['overall']['annual_return']:.2%} "
        f"oos={baselines['aggressive_v1']['oos_2024_2026']['total_return']:+.2%}"
    )
    for section_key, title in (
        ("vs_conservative_standard_gate", "vs conservative | standard gate (MDD≥-25%)"),
        ("vs_conservative_return_focused_gate", "vs conservative | return-focused gate (MDD≥-35%)"),
        ("vs_aggressive_return_focused_gate", "vs aggressive   | return-focused gate (MDD≥-35%)"),
    ):
        review = payload[section_key]
        promoted = [item["key"] for item in review.get("promoted") or []]
        print(f"\n--- {title} ---")
        if promoted:
            print(f"  PROMOTED: {', '.join(promoted)}")
        else:
            print("  PROMOTED: (none)")
        for item in review["candidates"]:
            flag = "PASS" if item["passes_gate"] else "fail"
            reasons = ",".join(item.get("fail_reasons") or []) or "-"
            print(
                f"  [{flag}] {item['key']:<45} oos_lift={item['oos_total_return_lift']:+7.2%} "
                f"mdd={item['overall_mdd']:7.2%} reasons={reasons}"
            )


def _print_aggressive_grid(payload: dict[str, Any]) -> None:
    print("\n=== P2.2 Aggressive ETF + vol25 MA120 权重网格 ===\n")
    rows = sorted(
        [row for row in payload["grid"] if row["within_mdd_budget"]],
        key=lambda row: row["overall"]["annual_return"],
        reverse=True,
    )
    for row in rows:
        overall = row["overall"]
        print(
            f"  etf={row['etf_weight']:.0%} stock={row['stock_weight']:.0%} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"oos={row['oos_2024_2026']['total_return']:+7.2%}"
        )
    best = payload.get("best_within_budget_by_ann")
    if best:
        o = best["overall"]
        print(
            f"\nBest (MDD≤35%): etf={best['etf_weight']:.0%} stock={best['stock_weight']:.0%} "
            f"ann={o['annual_return']:.2%} mdd={o['max_drawdown']:.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="MA120 Phase 2: gate review + aggressive weight grid.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--mode",
        choices=("all", "gate", "aggressive_grid"),
        default="all",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "start": args.start,
        "end": args.end,
        "mdd_budget": MDD_BUDGET,
        "vol25_preset": CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    }
    if args.mode in {"all", "gate"}:
        payload["promotion_reviews"] = run_promotion_reviews(start=args.start, end=args.end)
        _print_promotion_report(payload["promotion_reviews"])
    if args.mode in {"all", "aggressive_grid"}:
        payload["aggressive_vol25_weight_grid"] = run_combo_weight_grid(
            start=args.start,
            end=args.end,
            stock_preset_keys=(CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,),
            etf_weights=DEFAULT_ETF_WEIGHTS,
            industry_profile="aggressive",
        )
        _print_aggressive_grid(payload["aggressive_vol25_weight_grid"])

    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
