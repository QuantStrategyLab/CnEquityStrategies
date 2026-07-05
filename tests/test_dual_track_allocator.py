from __future__ import annotations

import pandas as pd

from scripts.research_cn_dual_track_combo_proxy_backtest import (
    _build_regime_combo_series,
    _metrics_from_returns,
    _scan_combo_weight_grid,
    _select_combo_weight,
    _regime_allocation_weights,
)


def _make_series(values: list[float]) -> pd.Series:
    index = pd.bdate_range("2024-01-02", periods=len(values))
    return pd.Series(values, index=index, dtype=float)


def test_regime_allocator_increases_industry_weight_in_stronger_trend() -> None:
    strong_industry = _make_series([0.006] * 220)
    weak_industry = _make_series([-0.002] * 220)
    dividend = _make_series([0.001] * 220)
    benchmark = _make_series([0.0015] * 220)
    as_of = strong_industry.index[-1]

    strong_weights = _regime_allocation_weights(
        as_of=as_of,
        industry_returns=strong_industry,
        dividend_returns=dividend,
        benchmark_returns=benchmark,
        base_industry_weight=0.70,
        base_dividend_weight=0.30,
    )
    weak_weights = _regime_allocation_weights(
        as_of=as_of,
        industry_returns=weak_industry,
        dividend_returns=dividend,
        benchmark_returns=benchmark,
        base_industry_weight=0.70,
        base_dividend_weight=0.30,
    )

    strong_industry_weight, strong_dividend_weight, strong_meta = strong_weights
    weak_industry_weight, weak_dividend_weight, weak_meta = weak_weights

    assert abs((strong_industry_weight + strong_dividend_weight) - 1.0) < 1e-12
    assert abs((weak_industry_weight + weak_dividend_weight) - 1.0) < 1e-12
    assert strong_industry_weight > weak_industry_weight
    assert strong_meta["regime_score"] > weak_meta["regime_score"]


def test_regime_combo_series_emits_month_end_allocations() -> None:
    dates = pd.bdate_range("2024-01-02", periods=160)
    industry = pd.Series([0.004] * len(dates), index=dates, dtype=float)
    dividend = pd.Series([0.001] * len(dates), index=dates, dtype=float)
    benchmark = pd.Series([0.0015] * len(dates), index=dates, dtype=float)

    combo, trace = _build_regime_combo_series(
        industry,
        dividend,
        benchmark,
        base_industry_weight=0.70,
        base_dividend_weight=0.30,
    )

    assert len(combo) == len(dates)
    assert trace
    assert trace[0]["rebalance_date"] < trace[0]["effective_date"]
    assert abs(trace[0]["industry_weight"] + trace[0]["dividend_weight"] - 1.0) < 1e-12
    assert combo.iloc[-1] > (0.70 * industry.iloc[-1] + 0.30 * dividend.iloc[-1])


def test_combo_weight_scan_prefers_more_industry_when_it_dominates() -> None:
    dates = pd.bdate_range("2024-01-02", periods=260)
    industry = pd.Series([0.004] * len(dates), index=dates, dtype=float)
    dividend = pd.Series([0.001] * len(dates), index=dates, dtype=float)
    industry_metrics = _metrics_from_returns(industry)

    rows = _scan_combo_weight_grid(
        industry,
        dividend,
        industry_metrics,
        industry_recent_total_return=industry_metrics["total_return"],
    )
    selected = _select_combo_weight(rows)

    assert rows
    assert selected is not None
    assert selected["industry_weight"] == max(row["industry_weight"] for row in rows)
    assert selected["within_mdd_budget"] is True
