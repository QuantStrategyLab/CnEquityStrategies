from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


RESEARCH_EVIDENCE_SCHEMA_VERSION = "cn_equity_research_evidence.v1"
RESEARCH_EVIDENCE_MISSING = "research_evidence_missing"
POINT_IN_TIME_INCOMPLETE = "point_in_time_incomplete"
HISTORICAL_MEMBERSHIP_INCOMPLETE = "historical_membership_incomplete"
HISTORICAL_CONSTITUENTS_INCOMPLETE = "historical_constituents_incomplete"
ADJUSTMENT_PROVENANCE_INCOMPLETE = "adjustment_provenance_incomplete"
UNIVERSE_PROVENANCE_INCOMPLETE = "universe_provenance_incomplete"
SURVIVORSHIP_BIAS_UNCONTROLLED = "survivorship_bias_uncontrolled"
RESEARCH_ONLY = "research_only"

_COMPLETENESS_REASON_CODES = {
    "point_in_time": POINT_IN_TIME_INCOMPLETE,
    "historical_membership_complete": HISTORICAL_MEMBERSHIP_INCOMPLETE,
    "historical_constituents_complete": HISTORICAL_CONSTITUENTS_INCOMPLETE,
    "adjustment_provenance_complete": ADJUSTMENT_PROVENANCE_INCOMPLETE,
    "universe_provenance_complete": UNIVERSE_PROVENANCE_INCOMPLETE,
    "survivorship_bias_controlled": SURVIVORSHIP_BIAS_UNCONTROLLED,
}
_STRUCTURAL_REASON_CODES = {
    RESEARCH_EVIDENCE_MISSING,
    "evidence_schema_invalid",
    "evidence_field_missing",
    "evidence_field_unknown",
    "evidence_field_invalid",
    "evidence_field_unexpected",
    "reason_codes_invalid",
    "reason_code_unknown",
    "evidence_inconsistent",
}
_SEMANTIC_REASON_CODES = frozenset({*_COMPLETENESS_REASON_CODES.values(), RESEARCH_ONLY})
_REQUIRED_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "research_only",
        "promotion_eligible",
        *_COMPLETENESS_REASON_CODES,
        "reason_codes",
    }
)


def _is_unknown(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() == "unknown")


def evaluate_research_evidence(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate the closed evidence contract and fail closed on any ambiguity."""
    if raw is None:
        return {
            "research_only": True,
            "promotion_eligible": False,
            "promotion_status": "NOT_PROMOTION_ELIGIBLE",
            "reason_codes": [RESEARCH_EVIDENCE_MISSING],
        }
    structural_reasons: set[str] = set()
    semantic_reasons: set[str] = set()

    if set(raw) - _REQUIRED_EVIDENCE_FIELDS:
        structural_reasons.add("evidence_field_unexpected")

    if "schema_version" not in raw:
        structural_reasons.add("evidence_field_missing")
    elif _is_unknown(raw["schema_version"]):
        structural_reasons.add("evidence_field_unknown")
    if raw.get("schema_version") != RESEARCH_EVIDENCE_SCHEMA_VERSION:
        structural_reasons.add("evidence_schema_invalid")

    for field, reason_code in _COMPLETENESS_REASON_CODES.items():
        if field not in raw:
            structural_reasons.add("evidence_field_missing")
            semantic_reasons.add(reason_code)
        elif _is_unknown(raw[field]):
            structural_reasons.add("evidence_field_unknown")
            semantic_reasons.add(reason_code)
        elif not isinstance(raw[field], bool):
            structural_reasons.add("evidence_field_invalid")
            semantic_reasons.add(reason_code)
        elif raw[field] is not True:
            semantic_reasons.add(reason_code)

    for field in ("research_only", "promotion_eligible"):
        if field not in raw:
            structural_reasons.add("evidence_field_missing")
        elif _is_unknown(raw[field]):
            structural_reasons.add("evidence_field_unknown")
        elif not isinstance(raw[field], bool):
            structural_reasons.add("evidence_field_invalid")

    if raw.get("research_only") is True:
        semantic_reasons.add(RESEARCH_ONLY)

    supplied_reasons: set[str] = set()
    if "reason_codes" not in raw:
        structural_reasons.add("evidence_field_missing")
        raw_codes: Any = None
    else:
        raw_codes = raw["reason_codes"]
    if _is_unknown(raw_codes):
        structural_reasons.add("evidence_field_unknown")
    elif not isinstance(raw_codes, (list, tuple)):
        structural_reasons.add("reason_codes_invalid")
    else:
        for code in raw_codes:
            if not isinstance(code, str) or code not in _SEMANTIC_REASON_CODES:
                structural_reasons.add("reason_code_unknown")
            else:
                supplied_reasons.add(code)
                semantic_reasons.add(code)

    for field, reason_code in _COMPLETENESS_REASON_CODES.items():
        if raw.get(field) is True and reason_code in supplied_reasons:
            structural_reasons.add("evidence_inconsistent")
    if raw.get("research_only") is False and RESEARCH_ONLY in supplied_reasons:
        structural_reasons.add("evidence_inconsistent")

    all_complete = all(raw.get(field) is True for field in _COMPLETENESS_REASON_CODES)
    expected_eligible = raw.get("research_only") is False and all_complete and not semantic_reasons
    if isinstance(raw.get("promotion_eligible"), bool) and raw["promotion_eligible"] != expected_eligible:
        structural_reasons.add("evidence_inconsistent")
    promotion_eligible = (
        expected_eligible
        and not structural_reasons
        and raw.get("promotion_eligible") is True
    )
    return {
        "research_only": raw.get("research_only") if isinstance(raw.get("research_only"), bool) else True,
        "promotion_eligible": promotion_eligible,
        "promotion_status": "PROMOTION_ELIGIBLE" if promotion_eligible else "NOT_PROMOTION_ELIGIBLE",
        "reason_codes": sorted(semantic_reasons | structural_reasons),
    }


def build_research_evidence(
    *,
    research_only: bool,
    promotion_eligible: bool,
    point_in_time: bool | None,
    historical_membership_complete: bool | None,
    historical_constituents_complete: bool | None,
    adjustment_provenance_complete: bool | None,
    universe_provenance_complete: bool | None,
    survivorship_bias_controlled: bool | None,
    reason_codes: tuple[str, ...] = (),
) -> dict[str, Any]:
    evidence = {
        "schema_version": RESEARCH_EVIDENCE_SCHEMA_VERSION,
        "research_only": research_only,
        "promotion_eligible": promotion_eligible,
        "point_in_time": point_in_time,
        "historical_membership_complete": historical_membership_complete,
        "historical_constituents_complete": historical_constituents_complete,
        "adjustment_provenance_complete": adjustment_provenance_complete,
        "universe_provenance_complete": universe_provenance_complete,
        "survivorship_bias_controlled": survivorship_bias_controlled,
        "reason_codes": list(reason_codes),
    }
    review = evaluate_research_evidence(evidence)
    structural_reasons = set(review["reason_codes"]) & _STRUCTURAL_REASON_CODES
    if structural_reasons:
        raise ValueError(f"invalid research evidence: {sorted(structural_reasons)}")
    evidence["reason_codes"] = review["reason_codes"]
    return evidence


def attach_research_evidence(
    payload: Mapping[str, Any],
    *,
    research_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    review = evaluate_research_evidence(research_evidence)
    return {
        **dict(payload),
        "research_evidence_schema_version": research_evidence.get("schema_version"),
        "research_only": review["research_only"],
        "promotion_eligible": review["promotion_eligible"],
        "promotion_status": review["promotion_status"],
        "reason_codes": review["reason_codes"],
        **{field: research_evidence.get(field) for field in _COMPLETENESS_REASON_CODES},
        "research_evidence": deepcopy(dict(research_evidence)),
    }


def evaluate_promotion(
    results: Mapping[str, dict[str, Any]],
    gate: Mapping[str, Any],
    *,
    baseline_key: str = "conservative_v1",
    research_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Score research variants against a promotion gate dict (see industry_etf_rotation_presets)."""
    baseline = results[baseline_key]
    baseline_oos = baseline["period_metrics"]["oos_2024_2026"]
    baseline_train = baseline["period_metrics"]["train_2021_2023"]
    baseline_bear = baseline["period_metrics"].get("bear_2021_2022", {})

    evidence_gate = evaluate_research_evidence(research_evidence)
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
        if not evidence_gate["promotion_eligible"]:
            passes = False
            fail_reasons.extend(evidence_gate["reason_codes"])
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
    promoted = [item for item in candidates if item["passes_gate"]]
    promotion_eligible = evidence_gate["promotion_eligible"] and bool(promoted)
    promotion_status = "PROMOTION_ELIGIBLE" if promotion_eligible else "NOT_PROMOTION_ELIGIBLE"
    return {
        "gate": dict(gate),
        "baseline_key": baseline_key,
        "baseline_oos": baseline_oos,
        "baseline_train": baseline_train,
        "baseline_bear": baseline_bear,
        "candidates": candidates,
        "promoted": promoted,
        "promotion_eligible": promotion_eligible,
        "promotion_status": promotion_status,
        "reason_codes": evidence_gate["reason_codes"],
        "research_evidence": deepcopy(dict(research_evidence)) if research_evidence is not None else None,
    }
