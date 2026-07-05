from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies.cn_chinext_growth_momentum_quality_snapshot import SAFE_HAVEN


def sample_chinext_factor_snapshot() -> pd.DataFrame:
    rows = [
        {
            "symbol": "300001",
            "sector": "software",
            "close_cny": 28.0,
            "adv20_cny": 80_000_000.0,
            "market_cap_cny": 25_000_000_000.0,
            "revenue_yoy": 0.32,
            "profit_yoy": 0.28,
            "revenue_acceleration_2q": 0.10,
            "roe_ttm": 0.18,
            "roe_stability_3y": 0.75,
            "gross_margin_stability_3y": 0.70,
            "mom_12_1": 0.24,
            "mom_6_1": 0.16,
            "sma200_gap": 0.12,
            "realized_vol_126": 0.28,
            "earnings_positive": True,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 1200,
        },
        {
            "symbol": "300002",
            "sector": "biotech",
            "close_cny": 44.0,
            "adv20_cny": 60_000_000.0,
            "market_cap_cny": 18_000_000_000.0,
            "revenue_yoy": 0.24,
            "profit_yoy": 0.21,
            "revenue_acceleration_2q": 0.06,
            "roe_ttm": 0.15,
            "roe_stability_3y": 0.68,
            "gross_margin_stability_3y": 0.66,
            "mom_12_1": 0.18,
            "mom_6_1": 0.12,
            "sma200_gap": 0.08,
            "realized_vol_126": 0.24,
            "earnings_positive": True,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 900,
        },
        {
            "symbol": "300003",
            "sector": "new_energy",
            "close_cny": 16.0,
            "adv20_cny": 55_000_000.0,
            "market_cap_cny": 14_000_000_000.0,
            "revenue_yoy": 0.04,
            "profit_yoy": -0.02,
            "revenue_acceleration_2q": -0.01,
            "roe_ttm": 0.08,
            "roe_stability_3y": 0.50,
            "gross_margin_stability_3y": 0.48,
            "mom_12_1": 0.05,
            "mom_6_1": 0.03,
            "sma200_gap": 0.01,
            "realized_vol_126": 0.20,
            "earnings_positive": True,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 800,
        },
        {
            "symbol": SAFE_HAVEN,
            "sector": "etf",
            "close_cny": 3.5,
            "adv20_cny": 1_000_000_000.0,
            "market_cap_cny": 0.0,
            "revenue_yoy": 0.0,
            "profit_yoy": 0.0,
            "revenue_acceleration_2q": 0.0,
            "roe_ttm": 0.0,
            "roe_stability_3y": 0.0,
            "gross_margin_stability_3y": 0.0,
            "mom_12_1": 0.0,
            "mom_6_1": 0.0,
            "sma200_gap": 0.0,
            "realized_vol_126": 0.12,
            "earnings_positive": True,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 3000,
        },
    ]
    return pd.DataFrame(rows)


def test_chinext_growth_momentum_quality_scores_and_filters() -> None:
    from cn_equity_strategies.strategies.cn_chinext_growth_momentum_quality_snapshot import score_candidates

    ranked = score_candidates(sample_chinext_factor_snapshot())

    assert not ranked.empty
    assert ranked.iloc[0]["symbol"] in {"300001", "300002"}
    assert SAFE_HAVEN not in set(ranked["symbol"])


def test_chinext_growth_momentum_quality_scores_low_unit_adv20_snapshot() -> None:
    from cn_equity_strategies.strategies.cn_chinext_growth_momentum_quality_snapshot import score_candidates

    snapshot = sample_chinext_factor_snapshot().copy()
    snapshot["adv20_cny"] = snapshot["adv20_cny"] / 10_000.0

    ranked = score_candidates(snapshot)

    assert not ranked.empty
    assert SAFE_HAVEN not in set(ranked["symbol"])


def test_chinext_growth_momentum_quality_compute_signals_returns_weights() -> None:
    from cn_equity_strategies.strategies.cn_chinext_growth_momentum_quality_snapshot import compute_signals

    weights, signal_desc, hard_defense, status_desc, metadata = compute_signals(
        sample_chinext_factor_snapshot(),
        current_holdings=set(),
        holdings_count=2,
    )

    assert weights
    assert SAFE_HAVEN in weights or sum(weights.values()) == 1.0
    assert "chinext growth momentum quality" in signal_desc
    assert metadata["snapshot_contract_version"] == "cn_chinext_growth_momentum_quality_snapshot.factor_snapshot.v1"
    assert isinstance(hard_defense, bool)
    assert "regime=" in status_desc
