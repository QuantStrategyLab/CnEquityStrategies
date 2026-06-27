from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies.cn_industry_etf_rotation import (
    DEFAULT_UNIVERSE_SYMBOLS,
    build_target_weights,
    compute_latest_signal,
    extract_managed_symbols,
)
from cn_equity_strategies.strategies.industry_etf_rotation_core import apply_sentiment_adjustment


def _history(*, days: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range("2023-06-01", periods=days)
    rows = []
    for symbol in extract_managed_symbols():
        price = 10.0 + (hash(symbol) % 5)
        volume = 1_000_000.0 + (hash(symbol) % 7) * 100_000
        for idx, day in enumerate(dates):
            price *= 1.0002 + (idx % 9) * 0.00005
            volume *= 1.0 + 0.02 * ((idx % 11) - 5) / 11
            rows.append({"date": day, "symbol": symbol, "close": price, "volume": max(volume, 1.0)})
    return pd.DataFrame(rows)


def test_industry_universe_excludes_global_gold_and_nasdaq():
    managed = extract_managed_symbols()
    assert "513100" not in managed
    assert "518880" not in managed
    assert "159819" in DEFAULT_UNIVERSE_SYMBOLS


def test_industry_rotation_builds_weights():
    weights, metadata = build_target_weights(_history(), min_history_days=220)
    assert weights
    assert metadata["sentiment_mode"] == "off"
    assert len(metadata["selected_symbols"]) <= 5


def test_sentiment_crowding_penalizes_high_turnover():
    rows = [{"symbol": "159819", "score": 2.0, "eligible": True, "volatility": 0.2}]
    adjusted = apply_sentiment_adjustment(
        rows,
        turnover_zscores={"159819": 2.0},
        sentiment_mode="flow_crowding",
        sentiment_weight=0.15,
        crowding_zscore_threshold=1.5,
        crowding_penalty=0.25,
    )
    assert adjusted[0]["score"] < 2.0


def test_industry_signal_respects_sentiment_off():
    signal = compute_latest_signal(_history(), min_history_days=220, sentiment_mode="off")
    assert signal["sentiment_mode"] == "off"
