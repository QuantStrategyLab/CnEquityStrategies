from __future__ import annotations

from typing import Any, Mapping


def evaluate_promotion(
    results: Mapping[str, dict[str, Any]],
    gate: Mapping[str, Any],
    *,
    baseline_key: str = "conservative_v1",
) -> dict[str, Any]:
    """Score research variants against a promotion gate dict (see industry_etf_rotation_presets)."""
    baseline = results[baseline_key]
    baseline_oos = baseline["period_metrics"]["oos_2024_2026"]
    baseline_train = baseline["period_metrics"]["train_2021_2023"]
    baseline_bear = baseline["period_metrics"].get("bear_2021_2022", {})

    candidates: list[dict[str, Any]] = []
    for key, row in results.items():
        if key == baseline_key:
            continue
        oos = row["period_metrics"]["oos_2024_2026"]
        train = row["period_metrics"]["train_2021_2023"]
        bear = row["period_metrics"].get("bear_2021_2022", {})
        oos_lift = float(oos["total_return"]) - float(baseline_oos["total_return"])
        mdd_delta = float(row["overall"]["max_drawdown"]) - float(baseline["overall"]["max_drawdown"])
        passes = (
            oos_lift >= float(gate["min_oos_total_return_lift"])
            and mdd_delta >= -float(gate["max_mdd_regression"])
        )
        fail_reasons: list[str] = []
        if oos_lift < float(gate["min_oos_total_return_lift"]):
            fail_reasons.append("oos_lift")
        if mdd_delta < -float(gate["max_mdd_regression"]):
            fail_reasons.append("mdd_vs_baseline")

        max_mdd_absolute = gate.get("max_mdd_absolute")
        if max_mdd_absolute is not None and float(row["overall"]["max_drawdown"]) < float(max_mdd_absolute):
            passes = False
            fail_reasons.append("max_mdd_absolute")

        max_bear_regression = gate.get("max_bear_total_return_regression")
        if max_bear_regression is not None and int(bear.get("days", 0)) > 0 and int(baseline_bear.get("days", 0)) > 0:
            bear_delta = float(bear["total_return"]) - float(baseline_bear["total_return"])
            if bear_delta < -float(max_bear_regression):
                passes = False
                fail_reasons.append("bear_period_regression")

        candidates.append(
            {
                "key": key,
                "label": row["label"],
                "passes_gate": passes,
                "fail_reasons": fail_reasons,
                "oos_total_return_lift": oos_lift,
                "mdd_vs_baseline": mdd_delta,
                "overall_mdd": float(row["overall"]["max_drawdown"]),
                "bear_total_return": float(bear.get("total_return", 0.0)),
                "bear_vs_baseline": (
                    float(bear["total_return"]) - float(baseline_bear["total_return"])
                    if int(bear.get("days", 0)) > 0 and int(baseline_bear.get("days", 0)) > 0
                    else None
                ),
                "train_total_return": train["total_return"],
                "oos_total_return": oos["total_return"],
            }
        )
    candidates.sort(key=lambda item: (item["passes_gate"], item["oos_total_return_lift"]), reverse=True)
    return {
        "gate": dict(gate),
        "baseline_key": baseline_key,
        "baseline_oos": baseline_oos,
        "baseline_train": baseline_train,
        "baseline_bear": baseline_bear,
        "candidates": candidates,
        "promoted": [item for item in candidates if item["passes_gate"]],
    }
