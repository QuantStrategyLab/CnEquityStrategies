from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cn_equity_strategies.backtest.promotion_gate import (
    RESEARCH_EVIDENCE_SCHEMA_VERSION,
    attach_research_evidence,
    build_research_evidence,
    evaluate_research_evidence,
    evaluate_promotion,
)


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_EVIDENCE_FIELDS = {
    "schema_version",
    "research_only",
    "promotion_eligible",
    "point_in_time",
    "historical_membership_complete",
    "historical_constituents_complete",
    "adjustment_provenance_complete",
    "universe_provenance_complete",
    "survivorship_bias_controlled",
    "reason_codes",
}


def _eligible_evidence() -> dict:
    return {
        "schema_version": RESEARCH_EVIDENCE_SCHEMA_VERSION,
        "research_only": False,
        "promotion_eligible": True,
        "point_in_time": True,
        "historical_membership_complete": True,
        "historical_constituents_complete": True,
        "adjustment_provenance_complete": True,
        "universe_provenance_complete": True,
        "survivorship_bias_controlled": True,
        "reason_codes": [],
    }


def _row() -> dict:
    return {
        "label": "candidate",
        "overall": {"max_drawdown": -0.1, "total_return": 0.8},
        "period_metrics": {
            "oos_2024_2026": {"total_return": 0.4, "days": 100},
            "train_2021_2023": {"total_return": 0.2, "days": 100},
            "bear_2021_2022": {"total_return": -0.1, "days": 100},
        },
    }


def test_non_pit_research_output_is_machine_readable_and_not_promotion_eligible():
    evidence = build_research_evidence(
        research_only=True,
        promotion_eligible=False,
        point_in_time=False,
        historical_membership_complete=False,
        historical_constituents_complete=False,
        adjustment_provenance_complete=False,
        universe_provenance_complete=False,
        survivorship_bias_controlled=False,
    )
    output = attach_research_evidence(
        {"strategy_full": {"total_return": 0.2}},
        research_evidence=evidence,
    )

    assert set(output["research_evidence"]) == REQUIRED_EVIDENCE_FIELDS
    assert output["research_only"] is True
    assert output["promotion_eligible"] is False
    assert output["promotion_status"] == "NOT_PROMOTION_ELIGIBLE"
    assert output["research_evidence_schema_version"] == RESEARCH_EVIDENCE_SCHEMA_VERSION
    assert output["point_in_time"] is False
    assert output["historical_membership_complete"] is False
    assert output["historical_constituents_complete"] is False
    assert output["adjustment_provenance_complete"] is False
    assert output["universe_provenance_complete"] is False
    assert output["survivorship_bias_controlled"] is False
    assert output["reason_codes"] == [
        "adjustment_provenance_incomplete",
        "historical_constituents_incomplete",
        "historical_membership_incomplete",
        "point_in_time_incomplete",
        "research_only",
        "survivorship_bias_uncontrolled",
        "universe_provenance_incomplete",
    ]


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda item: item.pop("point_in_time"), "evidence_field_missing"),
        (lambda item: item.__setitem__("point_in_time", None), "evidence_field_unknown"),
        (lambda item: item.__setitem__("point_in_time", "unknown"), "evidence_field_unknown"),
        (lambda item: item.__setitem__("unexpected", True), "evidence_field_unexpected"),
        (lambda item: item.__setitem__("schema_version", "v0"), "evidence_schema_invalid"),
        (lambda item: item.__setitem__("research_only", True), "evidence_inconsistent"),
        (
            lambda item: item.__setitem__("reason_codes", ["point_in_time_incomplete"]),
            "evidence_inconsistent",
        ),
    ],
)
def test_missing_unknown_unexpected_or_inconsistent_evidence_fails_closed(mutate, reason_code):
    evidence = _eligible_evidence()
    mutate(evidence)

    review = evaluate_research_evidence(evidence)

    assert review["promotion_eligible"] is False
    assert review["promotion_status"] == "NOT_PROMOTION_ELIGIBLE"
    assert reason_code in review["reason_codes"]


def test_promotion_gate_rejects_metrics_when_research_evidence_is_incomplete():
    evidence = build_research_evidence(
        research_only=True,
        promotion_eligible=False,
        point_in_time=False,
        historical_membership_complete=False,
        historical_constituents_complete=False,
        adjustment_provenance_complete=False,
        universe_provenance_complete=False,
        survivorship_bias_controlled=False,
    )
    row = _row()

    review = evaluate_promotion(
        {"conservative_v1": row, "candidate": row},
        {"min_oos_total_return_lift": 0.0, "max_mdd_regression": 0.05},
        research_evidence=evidence,
    )

    assert review["promoted"] == []
    assert review["promotion_eligible"] is False
    assert review["promotion_status"] == "NOT_PROMOTION_ELIGIBLE"
    assert "point_in_time_incomplete" in review["reason_codes"]


def test_returned_nested_evidence_cannot_mutate_future_results():
    evidence = build_research_evidence(
        research_only=True,
        promotion_eligible=False,
        point_in_time=False,
        historical_membership_complete=False,
        historical_constituents_complete=False,
        adjustment_provenance_complete=False,
        universe_provenance_complete=False,
        survivorship_bias_controlled=False,
    )
    expected_reason_codes = list(evidence["reason_codes"])

    attached = attach_research_evidence({}, research_evidence=evidence)
    attached["research_evidence"]["reason_codes"].append("consumer_mutation")
    promoted = evaluate_promotion(
        {"conservative_v1": _row(), "candidate": _row()},
        {"min_oos_total_return_lift": 0.0, "max_mdd_regression": 0.05},
        research_evidence=evidence,
    )
    promoted["research_evidence"]["reason_codes"].append("consumer_mutation")

    assert evidence["reason_codes"] == expected_reason_codes
    assert attach_research_evidence({}, research_evidence=evidence)["reason_codes"] == expected_reason_codes


@pytest.mark.parametrize(
    ("path", "function_names", "evidence_name"),
    [
        (
            "scripts/research_cn_industry_etf_rotation_aggressive_matrix.py",
            ("evaluate_promotion", "attach_research_evidence"),
            "INDUSTRY_ETF_RESEARCH_EVIDENCE",
        ),
        (
            "scripts/research_cn_momentum_stock_rotation_proxy.py",
            ("evaluate_promotion", "attach_research_evidence"),
            "MOMENTUM_STOCK_RESEARCH_EVIDENCE",
        ),
        (
            "scripts/research_cn_thematic_stock_rotation_proxy.py",
            ("evaluate_promotion", "attach_research_evidence"),
            "THEMATIC_STOCK_RESEARCH_EVIDENCE",
        ),
        (
            "scripts/research_cn_dividend_quality_snapshot_proxy_backtest.py",
            ("attach_research_evidence",),
            "DIVIDEND_SNAPSHOT_RESEARCH_EVIDENCE",
        ),
    ],
)
def test_production_research_outputs_pass_explicit_evidence(path, function_names, evidence_name):
    tree = ast.parse((ROOT / path).read_text())
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert evidence_name in names
    for function_name in function_names:
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function_name
        ]
        assert calls
        assert all(
            any(
                keyword.arg == "research_evidence"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == evidence_name
                for keyword in call.keywords
            )
            for call in calls
        )
