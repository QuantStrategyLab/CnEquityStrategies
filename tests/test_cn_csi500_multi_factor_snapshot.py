from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies import cn_csi500_multi_factor_snapshot as strategy


def _factor_snapshot(*, n: int = 30) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "symbol": f"{600000 + i:06d}",
                "sector": "科技" if i % 3 == 0 else "消费" if i % 3 == 1 else "制造",
                "close": 20.0 + i * 2.0,
                "adv20_cny": 100_000_000.0 + i * 10_000_000.0,
                "market_cap_cny": 10_000_000_000.0 + i * 1_000_000_000.0,
                "roe_ttm": 0.08 + i * 0.005,
                "earnings_positive": True,
                "mom_6_1": 0.05 + i * 0.02,
                "mom_12_1": 0.08 + i * 0.03,
                "rel_mom_6m_vs_benchmark": 0.02 + i * 0.015,
                "sma200_gap": 0.03 + i * 0.01,
                "realized_vol_126": 0.25 - i * 0.005,
                "maxdd_126": -0.10 - i * 0.01,
            }
        )
    return pd.DataFrame(rows)


def test_defaults():
    assert strategy.PROFILE_NAME == "cn_csi500_multi_factor_snapshot"
    assert strategy.SIGNAL_SOURCE == "feature_snapshot"
    assert strategy.SAFE_HAVEN == "510300"
    assert strategy.DEFAULT_HOLDINGS_COUNT == 10
    assert strategy.DEFAULT_SINGLE_NAME_CAP == 0.12
    assert strategy.DEFAULT_RISK_ON_EXPOSURE == 1.0


def test_score_candidates_ranks_by_multi_factor():
    snapshot = _factor_snapshot()
    ranked = strategy.score_candidates(snapshot)
    assert not ranked.empty
    assert "rank" in ranked.columns
    assert "score" in ranked.columns
    assert "mom_6_1" in ranked.columns
    assert "rel_mom_6m_vs_benchmark" in ranked.columns
    # Higher-ranked should have higher scores
    scores = ranked["score"].dropna().tolist()
    assert scores == sorted(scores, reverse=True)


def test_score_candidates_hold_bonus():
    snapshot = _factor_snapshot()
    top_symbol = snapshot.iloc[0]["symbol"]
    ranked_with = strategy.score_candidates(snapshot, current_holdings={top_symbol})
    ranked_without = strategy.score_candidates(snapshot)
    score_with = ranked_with.loc[ranked_with["symbol"] == top_symbol, "score"].iloc[0]
    score_without = ranked_without.loc[ranked_without["symbol"] == top_symbol, "score"].iloc[0]
    assert score_with >= score_without


def test_build_target_weights_produces_weights():
    snapshot = _factor_snapshot()
    weights, ranked, metadata = strategy.build_target_weights(snapshot)
    assert weights
    assert 0 < sum(weights.values()) <= 1.0
    assert metadata["selected_count"] > 0
    assert metadata["regime"] in ("risk_on", "soft_defense", "hard_defense")


def test_compute_signals_returns_full_payload():
    snapshot = _factor_snapshot()
    weights, signal_desc, has_cash, status_desc, metadata = strategy.compute_signals(
        snapshot, current_holdings=set()
    )
    assert weights
    assert "snapshot_contract_version" in metadata
    assert metadata["actionable"] is True
