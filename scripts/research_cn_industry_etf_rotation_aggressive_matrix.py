#!/usr/bin/env python3
"""Research matrix: conservative v1 baseline vs aggressive industry rotation variants."""

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

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_rotation
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (
    AGGRESSIVE_RESEARCH_PRESETS,
    CONSERVATIVE_V1_PRESET,
    PROMOTION_GATE,
)
from research_cn_industry_etf_rotation_validation import (
    VALIDATION_PERIODS,
    _download_market_history,
    _period_metrics,
)


def _run_preset(market_history, key: str, preset: dict[str, Any]) -> dict[str, Any]:
    rebalance_frequency = str(preset.get("rebalance_frequency") or "monthly")
    config = ProxyBacktestConfig(
        min_history_days=int(preset.get("min_history_days") or industry_rotation.DEFAULT_MIN_HISTORY_DAYS),
        rebalance_frequency=rebalance_frequency,  # type: ignore[arg-type]
    )
    strategy_kwargs = {
        key: value
        for key, value in preset.items()
        if key
        not in {
            "profile_variant",
            "label",
            "rebalance_frequency",
            "execution_cash_reserve_ratio",
        }
    }

    def signal_fn(history: Any, **kwargs: Any):
        merged = {**kwargs, **strategy_kwargs}
        return industry_rotation.build_target_weights(history, **merged)

    backtest = run_proxy_backtest(
        market_history,
        signal_fn,
        config=config,
        universe_symbols=tuple(preset["universe_symbols"]),
        strategy_kwargs=strategy_kwargs,
    )
    period_metrics = {
        period: _period_metrics(backtest.daily_returns, start, end)
        for period, (start, end) in VALIDATION_PERIODS.items()
    }
    return {
        "key": key,
        "label": preset.get("label", key),
        "profile_variant": preset.get("profile_variant"),
        "overall": backtest.metrics,
        "period_metrics": period_metrics,
        "rebalance_count": len(backtest.rebalance_events),
    }


def _evaluate_promotion(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline = results["conservative_v1"]
    baseline_oos = baseline["period_metrics"]["oos_2024_2026"]
    baseline_train = baseline["period_metrics"]["train_2021_2023"]

    candidates: list[dict[str, Any]] = []
    for key, row in results.items():
        if key == "conservative_v1":
            continue
        oos = row["period_metrics"]["oos_2024_2026"]
        train = row["period_metrics"]["train_2021_2023"]
        oos_lift = float(oos["total_return"]) - float(baseline_oos["total_return"])
        mdd_delta = float(row["overall"]["max_drawdown"]) - float(baseline["overall"]["max_drawdown"])
        passes = (
            oos_lift >= float(PROMOTION_GATE["min_oos_total_return_lift"])
            and mdd_delta >= -float(PROMOTION_GATE["max_mdd_regression"])
        )
        candidates.append(
            {
                "key": key,
                "label": row["label"],
                "passes_gate": passes,
                "oos_total_return_lift": oos_lift,
                "mdd_vs_baseline": mdd_delta,
                "train_total_return": train["total_return"],
                "oos_total_return": oos["total_return"],
            }
        )
    candidates.sort(key=lambda item: (item["passes_gate"], item["oos_total_return_lift"]), reverse=True)
    return {
        "gate": PROMOTION_GATE,
        "baseline_oos": baseline_oos,
        "baseline_train": baseline_train,
        "candidates": candidates,
        "promoted": [item for item in candidates if item["passes_gate"]],
    }


def run_matrix(*, start: str, end: str, suite: str = "etf") -> dict[str, Any]:
    if suite == "stock":
        from research_cn_thematic_stock_rotation_proxy import run_stock_thematic_matrix

        return run_stock_thematic_matrix(start=start, end=end)

    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    market_history = _download_market_history(start=download_start, end=end)
    presets = {"conservative_v1": CONSERVATIVE_V1_PRESET, **AGGRESSIVE_RESEARCH_PRESETS}
    results = {key: _run_preset(market_history, key, preset) for key, preset in presets.items()}
    promotion = _evaluate_promotion(results)
    return {
        "start": start,
        "end": end,
        "suite": suite,
        "status": "research_only",
        "conservative_baseline": "conservative_v1",
        "variants": results,
        "promotion_review": promotion,
    }


def _print_report(payload: dict[str, Any]) -> None:
    if payload.get("active_symbols") is not None:
        from research_cn_thematic_stock_rotation_proxy import _print_report as _print_stock_report

        _print_stock_report(payload)
        return

    print("\n=== 行业 ETF 轮动 — Conservative v1 vs Aggressive research ===\n")
    rows = sorted(payload["variants"].values(), key=lambda item: item["overall"]["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        marker = "*" if row["key"] == "conservative_v1" else " "
        print(
            f"{index:2}.{marker} {row['label']:<44} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print("\n=== Promotion gate (OOS 2024–2026 vs conservative v1) ===")
    for item in payload["promotion_review"]["candidates"]:
        flag = "PASS" if item["passes_gate"] else "fail"
        print(
            f"  [{flag}] {item['key']:<28} oos_lift={item['oos_total_return_lift']:+7.2%} "
            f"mdd_delta={item['mdd_vs_baseline']:+.2%}"
        )
    promoted = payload["promotion_review"]["promoted"]
    if promoted:
        print("\nCandidates passing gate:", ", ".join(item["key"] for item in promoted))
    else:
        print("\nNo aggressive variant passed promotion gate yet.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative v1 vs aggressive industry rotation matrix.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--suite", choices=("etf", "stock"), default="etf")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run_matrix(start=args.start, end=args.end, suite=args.suite)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    _print_report(payload)


if __name__ == "__main__":
    main()
