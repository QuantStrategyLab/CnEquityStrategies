#!/usr/bin/env python3
"""Sweep dividend quality snapshot parameters and evaluate portfolio quality impact.

Creates all combinations of user-defined parameter grids, runs
build_target_weights for each, and reports which parameters most affect
holdings count, regime shifts, and yield capture.

Usage:
    python scripts/research_cn_dividend_quality_param_sweep.py
    python scripts/research_cn_dividend_quality_param_sweep.py \\
        --factor-snapshot /custom/path.csv \\
        --output-json results.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass, field as dataclass_field, asdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (SRC,):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as strategy  # noqa: E402


# ---------------------------------------------------------------------------
# Parameter grids
# ---------------------------------------------------------------------------

RISK_ON_EXPOSURE_GRID = [1.0, 1.15, 1.3]
MIN_DIVIDEND_YIELD_GRID = [0.020, 0.025]
MIN_MARKET_CAP_CNY_GRID = [3e9, 5e9]
MIN_ADV20_CNY_GRID = [20e6, 30e6]
MIN_ROE_TTM_GRID = [0.02, 0.04, 0.06]
MAX_PAYOUT_RATIO_GRID = [0.90, 1.20]
SOFT_BREADTH_THRESHOLD_GRID = [0.30, 0.40]

# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    risk_on_exposure: float
    min_dividend_yield: float
    min_market_cap_cny: float
    min_adv20_cny: float
    min_roe_ttm: float
    max_payout_ratio: float
    soft_breadth_threshold: float
    regime: str
    breadth_ratio: float
    target_stock_weight: float
    realized_stock_weight: float
    selected_count: int
    candidate_count: int
    safe_haven_weight: float
    selected_symbols: tuple[str, ...] = dataclass_field(default_factory=tuple)

    @property
    def yield_capture_heuristic(self) -> float:
        """Heuristic for 'yield capture': more selected stocks * higher exposure."""
        return float(self.realized_stock_weight) * float(self.selected_count)


def _run_sweep(factor_snapshot: pd.DataFrame) -> list[SweepResult]:
    """Iterate all parameter combos and return results."""
    results: list[SweepResult] = []
    for risk_on, min_yield, min_cap, min_adv, min_roe, max_payout, soft_thresh in itertools.product(
        RISK_ON_EXPOSURE_GRID,
        MIN_DIVIDEND_YIELD_GRID,
        MIN_MARKET_CAP_CNY_GRID,
        MIN_ADV20_CNY_GRID,
        MIN_ROE_TTM_GRID,
        MAX_PAYOUT_RATIO_GRID,
        SOFT_BREADTH_THRESHOLD_GRID,
    ):
        params: dict[str, Any] = dict(
            risk_on_exposure=risk_on,
            min_dividend_yield=min_yield,
            min_market_cap_cny=min_cap,
            min_adv20_cny=min_adv,
            min_roe_ttm=min_roe,
            max_payout_ratio=max_payout,
            soft_breadth_threshold=soft_thresh,
        )
        _weights, _ranked, metadata = strategy.build_target_weights(
            factor_snapshot,
            **params,
        )
        results.append(
            SweepResult(
                risk_on_exposure=risk_on,
                min_dividend_yield=min_yield,
                min_market_cap_cny=min_cap,
                min_adv20_cny=min_adv,
                min_roe_ttm=min_roe,
                max_payout_ratio=max_payout,
                soft_breadth_threshold=soft_thresh,
                regime=str(metadata.get("regime", "?")),
                breadth_ratio=float(metadata.get("breadth_ratio", 0.0)),
                target_stock_weight=float(metadata.get("target_stock_weight", 0.0)),
                realized_stock_weight=float(metadata.get("realized_stock_weight", 0.0)),
                selected_count=int(metadata.get("selected_count", 0)),
                candidate_count=int(metadata.get("candidate_count", 0)),
                safe_haven_weight=float(metadata.get("safe_haven_weight", 0.0)),
                selected_symbols=tuple(str(s) for s in metadata.get("selected_symbols", ())),
            )
        )
    return results


def _sort_key(r: SweepResult) -> tuple:
    """Sort by yield_capture_heuristic descending."""
    return (-r.yield_capture_heuristic,)


def _analyze(results: list[SweepResult]) -> str:
    """Produce a textual analysis of the sweep."""
    if not results:
        return "No results to analyze."

    df = pd.DataFrame([asdict(r) for r in results])
    # Add computed column from the SweepResult property
    df["yield_capture_heuristic"] = df["realized_stock_weight"] * df["selected_count"]
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("DIVIDEND QUALITY PARAMETER SWEEP REPORT")
    lines.append("=" * 72)
    lines.append("")

    # -- Summary statistics
    lines.append(f"Total combos tested: {len(results)}")
    lines.append(
        f"Grid: risk_on_exposure={RISK_ON_EXPOSURE_GRID}, "
        f"min_div_yield={MIN_DIVIDEND_YIELD_GRID}, "
        f"min_mkt_cap={MIN_MARKET_CAP_CNY_GRID}, "
        f"min_adv20={MIN_ADV20_CNY_GRID}, "
        f"min_roe_ttm={MIN_ROE_TTM_GRID}, "
        f"max_payout_ratio={MAX_PAYOUT_RATIO_GRID}, "
        f"soft_breadth_threshold={SOFT_BREADTH_THRESHOLD_GRID}"
    )
    lines.append("")

    # -- Holdings count sensitivity
    lines.append("-" * 72)
    lines.append("HOLDINGS COUNT SENSITIVITY")
    lines.append("-" * 72)
    lines.append(f"selected_count: min={df['selected_count'].min()}  "
                 f"max={df['selected_count'].max()}  "
                 f"mean={df['selected_count'].mean():.1f}  "
                 f"std={df['selected_count'].std():.1f}")
    lines.append(f"candidate_count: min={df['candidate_count'].min()}  "
                 f"max={df['candidate_count'].max()}  "
                 f"mean={df['candidate_count'].mean():.1f}  "
                 f"std={df['candidate_count'].std():.1f}")
    lines.append("")

    # Group by each parameter to show marginal effect
    for param, label in [
        ("min_dividend_yield", "min_dividend_yield"),
        ("min_market_cap_cny", "min_market_cap_cny"),
        ("min_adv20_cny", "min_adv20_cny"),
        ("risk_on_exposure", "risk_on_exposure"),
        ("min_roe_ttm", "min_roe_ttm"),
        ("max_payout_ratio", "max_payout_ratio"),
        ("soft_breadth_threshold", "soft_breadth_threshold"),
    ]:
        grouped = df.groupby(param)["selected_count"]
        lines.append(f"  By {label}:")
        for val, grp in grouped:
            lines.append(f"    {val:>12}: count={grp.mean():.1f}  "
                         f"(min={grp.min()}, max={grp.max()})")
    lines.append("")

    # -- Regime analysis
    lines.append("-" * 72)
    lines.append("REGIME / BREADTH ANALYSIS")
    lines.append("-" * 72)
    regime_counts = df["regime"].value_counts()
    for regime in ["risk_on", "soft_defense", "hard_defense"]:
        cnt = regime_counts.get(regime, 0)
        lines.append(f"  {regime:>15}: {cnt} combos ({cnt / len(results) * 100:.0f}%)")
    lines.append("")
    lines.append(f"breadth_ratio range: {df['breadth_ratio'].min():.4f} – "
                 f"{df['breadth_ratio'].max():.4f}")
    lines.append("")

    # Show which param crosses cause regime switch
    lines.append("  Regime switches by param slices:")
    for field, field_label in [
        ("min_dividend_yield", "min_dividend_yield"),
        ("min_market_cap_cny", "min_market_cap_cny"),
        ("min_adv20_cny", "min_adv20_cny"),
    ]:
        pivot = df.groupby(field)["regime"].apply(lambda x: x.value_counts().to_dict())
        lines.append(f"    {field_label}: {pivot.to_dict()}")
    lines.append("")

    # -- Target vs realized stock weight
    lines.append("-" * 72)
    lines.append("EXPOSURE ANALYSIS")
    lines.append("-" * 72)
    lines.append(f"target_stock_weight: min={df['target_stock_weight'].min():.3f}  "
                 f"max={df['target_stock_weight'].max():.3f}")
    lines.append(f"realized_stock_weight: min={df['realized_stock_weight'].min():.3f}  "
                 f"max={df['realized_stock_weight'].max():.3f}")
    lines.append("")

    # -- Yield capture heuristic
    lines.append("-" * 72)
    lines.append("TOP 10 BY YIELD CAPTURE HEURISTIC (realized_stock_weight * selected_count)")
    lines.append("-" * 72)
    sorted_df = df.sort_values("yield_capture_heuristic", ascending=False).head(10)
    display_cols = [
        "risk_on_exposure", "min_dividend_yield", "min_market_cap_cny", "min_adv20_cny",
        "min_roe_ttm", "max_payout_ratio", "soft_breadth_threshold",
        "regime", "breadth_ratio", "selected_count", "candidate_count",
        "realized_stock_weight", "yield_capture_heuristic",
    ]
    lines.append(sorted_df[display_cols].to_string(index=False))
    lines.append("")

    # -- Bottom 5
    lines.append("-" * 72)
    lines.append("BOTTOM 5 BY YIELD CAPTURE")
    lines.append("-" * 72)
    bottom_df = df.sort_values("yield_capture_heuristic", ascending=True).head(5)
    lines.append(bottom_df[display_cols].to_string(index=False))
    lines.append("")

    # -- Recommended top 3
    lines.append("-" * 72)
    lines.append("RECOMMENDED TOP 3 PARAMETER SETS")
    lines.append("-" * 72)
    top3 = df.sort_values("yield_capture_heuristic", ascending=False).head(3)
    for i, (_, row) in enumerate(top3.iterrows(), 1):
        lines.append(f"  #{i}:")
        lines.append(f"       risk_on_exposure    = {row['risk_on_exposure']}")
        lines.append(f"       min_dividend_yield   = {row['min_dividend_yield']}")
        lines.append(f"       min_market_cap_cny   = {row['min_market_cap_cny']:.0e}")
        lines.append(f"       min_adv20_cny        = {row['min_adv20_cny']:.0e}")
        lines.append(f"       min_roe_ttm          = {row['min_roe_ttm']}")
        lines.append(f"       max_payout_ratio     = {row['max_payout_ratio']}")
        lines.append(f"       soft_breadth_threshold = {row['soft_breadth_threshold']}")
        lines.append(f"       regime               = {row['regime']}")
        lines.append(f"       breadth_ratio        = {row['breadth_ratio']:.4f}")
        lines.append(f"       selected_count       = {int(row['selected_count'])}")
        lines.append(f"       candidate_count      = {int(row['candidate_count'])}")
        lines.append(f"       realized_stock_weight = {row['realized_stock_weight']:.3f}")
        lines.append(f"       yield_capture         = {row['yield_capture_heuristic']:.2f}")
        lines.append("")

    lines.append("=" * 72)
    return "\n".join(lines)


def _resolve_factor_snapshot(arg_path: str | None) -> str:
    if arg_path:
        p = Path(arg_path)
        if p.exists():
            return str(p.resolve())
        raise FileNotFoundError(f"Specified --factor-snapshot not found: {arg_path}")
    # Try default path
    default = (
        Path.home()
        / "Projects"
        / "CnEquitySnapshotPipelines"
        / "data"
        / "output"
        / "dividend_quality"
        / "cn_dividend_quality_snapshot_factor_snapshot_latest.csv"
    )
    if default.exists():
        return str(default.resolve())
    raise FileNotFoundError(
        f"No factor snapshot found at default location:\n  {default}\n"
        "Use --factor-snapshot to specify the path explicitly."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep dividend quality snapshot parameters."
    )
    parser.add_argument(
        "--factor-snapshot",
        type=str,
        default=None,
        help="Path to factor snapshot CSV. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional path to save full sweep results as JSON.",
    )
    args = parser.parse_args()

    snapshot_path = _resolve_factor_snapshot(args.factor_snapshot)
    print(f"Loading factor snapshot: {snapshot_path}")
    factor_snapshot = pd.read_csv(snapshot_path)
    print(f"Loaded {len(factor_snapshot)} rows, columns={list(factor_snapshot.columns)}")
    print()

    results = _run_sweep(factor_snapshot)
    print(f"Completed {len(results)} parameter combinations.")
    print()

    report = _analyze(results)
    print(report)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "grid": {
                "risk_on_exposure": RISK_ON_EXPOSURE_GRID,
                "min_dividend_yield": MIN_DIVIDEND_YIELD_GRID,
                "min_market_cap_cny": MIN_MARKET_CAP_CNY_GRID,
                "min_adv20_cny": MIN_ADV20_CNY_GRID,
                "min_roe_ttm": MIN_ROE_TTM_GRID,
                "max_payout_ratio": MAX_PAYOUT_RATIO_GRID,
                "soft_breadth_threshold": SOFT_BREADTH_THRESHOLD_GRID,
            },
            "results": [asdict(r) for r in results],
        }
        output_path.write_text(json.dumps(payload, indent=2, default=str))
        print(f"Full results saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
