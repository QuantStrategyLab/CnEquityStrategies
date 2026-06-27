from __future__ import annotations

from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion


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
    review = evaluate_promotion(results, gate)
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
    review = evaluate_promotion(results, gate)
    assert review["promoted"] == []
    assert "max_mdd_absolute" in review["candidates"][0]["fail_reasons"]
