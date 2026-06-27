from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies.cn_dividend_quality_snapshot import SAFE_HAVEN


def sample_factor_snapshot() -> pd.DataFrame:
    rows = [
        {
            "symbol": "600519",
            "sector": "consumer",
            "close_cny": 1680.0,
            "adv20_cny": 800_000_000.0,
            "market_cap_cny": 2_000_000_000_000.0,
            "dividend_yield_ttm": 0.035,
            "dividend_stability_3y": 0.85,
            "earnings_positive": True,
            "payout_ratio": 0.45,
            "roe_ttm": 0.28,
            "roe_stability_3y": 0.80,
            "realized_vol_126": 0.22,
            "mom_12_1": 0.08,
            "sma200_gap": 0.05,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 4000,
        },
        {
            "symbol": "601088",
            "sector": "energy",
            "close_cny": 28.0,
            "adv20_cny": 120_000_000.0,
            "market_cap_cny": 60_000_000_000.0,
            "dividend_yield_ttm": 0.055,
            "dividend_stability_3y": 0.78,
            "earnings_positive": True,
            "payout_ratio": 0.55,
            "roe_ttm": 0.16,
            "roe_stability_3y": 0.72,
            "realized_vol_126": 0.18,
            "mom_12_1": 0.12,
            "sma200_gap": 0.08,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 3000,
        },
        {
            "symbol": "000001",
            "sector": "finance",
            "close_cny": 12.0,
            "adv20_cny": 200_000_000.0,
            "market_cap_cny": 230_000_000_000.0,
            "dividend_yield_ttm": 0.048,
            "dividend_stability_3y": 0.70,
            "earnings_positive": True,
            "payout_ratio": 0.35,
            "roe_ttm": 0.11,
            "roe_stability_3y": 0.65,
            "realized_vol_126": 0.16,
            "mom_12_1": 0.04,
            "sma200_gap": 0.03,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 8000,
        },
        {
            "symbol": SAFE_HAVEN,
            "sector": "index",
            "close_cny": 4.0,
            "adv20_cny": 1_000_000_000.0,
            "market_cap_cny": 0.0,
            "dividend_yield_ttm": 0.02,
            "dividend_stability_3y": 0.50,
            "earnings_positive": True,
            "payout_ratio": 0.0,
            "roe_ttm": 0.10,
            "roe_stability_3y": 0.50,
            "realized_vol_126": 0.14,
            "mom_12_1": 0.01,
            "sma200_gap": 0.01,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 3000,
        },
    ]
    return pd.DataFrame(rows)


def test_dividend_quality_scores_candidates():
    from cn_equity_strategies.strategies.cn_dividend_quality_snapshot import score_candidates

    ranked = score_candidates(sample_factor_snapshot())
    assert not ranked.empty
    assert ranked.iloc[0]["symbol"] in {"601088", "600519", "000001"}


def test_dividend_quality_compute_signals_returns_weights():
    from cn_equity_strategies.strategies.cn_dividend_quality_snapshot import compute_signals

    weights, _signal_desc, _hard_defense, _status_desc, metadata = compute_signals(
        sample_factor_snapshot(),
        current_holdings=set(),
        holdings_count=2,
    )
    assert weights
    assert metadata["snapshot_contract_version"] == "cn_dividend_quality_snapshot.factor_snapshot.v1"
