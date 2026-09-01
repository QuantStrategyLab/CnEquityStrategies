from __future__ import annotations

from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion


def _eligible_research_evidence() -> dict:
    return {
        "schema_version": "cn_equity_research_evidence.v1",
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


def _row(*, total: float, mdd: float, oos: float, bear: float) -> dict:
    return {
        "label": "variant",
        "overall": {"max_drawdown": mdd, "total_return": total},
        "period_metrics": {
            "oos_2024_2026": {"total_return": oos, "days": 100},
            "train_2021_2023": {"total_return": 0.1, "days": 100},
            "bear_2021_2022": {"total_return": bear, "days": 100},
        },
    }


def test_evaluate_promotion_passes_when_oos_and_mdd_ok():
    gate = {
        "min_oos_total_return_lift": 0.05,
        "max_mdd_regression": 0.05,
    }
    results = {
        "conservative_v1": _row(total=0.8, mdd=-0.15, oos=0.2, bear=-0.03),
        "candidate": _row(total=0.9, mdd=-0.15, oos=0.30, bear=-0.05),
    }
    review = evaluate_promotion(results, gate, research_evidence=_eligible_research_evidence())
    assert review["promoted"][0]["key"] == "candidate"


def test_evaluate_promotion_rejects_deep_mdd_absolute():
    gate = {
        "min_oos_total_return_lift": 0.05,
        "max_mdd_regression": 0.05,
        "max_mdd_absolute": -0.28,
    }
    results = {
        "conservative_v1": _row(total=0.8, mdd=-0.15, oos=0.2, bear=-0.03),
        "candidate": _row(total=1.5, mdd=-0.40, oos=0.50, bear=-0.05),
    }
    review = evaluate_promotion(results, gate, research_evidence=_eligible_research_evidence())
    assert review["promoted"] == []
    assert "max_mdd_absolute" in review["candidates"][0]["fail_reasons"]


def test_evaluate_promotion_without_research_evidence_fails_closed():
    gate = {
        "min_oos_total_return_lift": 0.05,
        "max_mdd_regression": 0.05,
    }
    results = {
        "conservative_v1": _row(total=0.8, mdd=-0.15, oos=0.2, bear=-0.03),
        "candidate": _row(total=0.9, mdd=-0.15, oos=0.30, bear=-0.05),
    }

    review = evaluate_promotion(results, gate)

    assert review["promoted"] == []
    assert review["promotion_eligible"] is False
    assert review["promotion_status"] == "NOT_PROMOTION_ELIGIBLE"
    assert review["reason_codes"] == ["research_evidence_missing"]
    assert "research_evidence_missing" in review["candidates"][0]["fail_reasons"]
