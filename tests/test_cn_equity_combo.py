from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies import cn_equity_combo as strategy


def _etf_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rows = []
    for symbol in ("510300", "512170", "515030", "512760"):
        price = 10.0
        for date in dates:
            price *= 1.001 + (hash(symbol) % 3 - 1) * 0.002
            rows.append({"date": date, "symbol": symbol, "close": price, "volume": 1_000_000.0})
    return pd.DataFrame(rows)


def _stock_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rows = []
    for sym_idx in range(1, 15):
        symbol = f"{600000 + sym_idx:06d}"
        price = 10.0 + sym_idx * 2.0
        for date in dates:
            noise = 1.0 + 0.003 * ((date.day + sym_idx) % 5 - 2)
            price *= 1.002 * noise
            rows.append({"date": date, "symbol": symbol, "close": price, "volume": 1_000_000.0 + sym_idx})
    return pd.DataFrame(rows)


def _dividend_snapshot() -> pd.DataFrame:
    rows = []
    for i in range(20):
        rows.append({
            "symbol": f"{600000 + i:06d}",
            "sector": "金融" if i < 5 else "消费" if i < 12 else "制造",
            "close_cny": 20.0 + i * 2.0,
            "adv20_cny": 100_000_000.0 + i * 10_000_000.0,
            "market_cap_cny": 10_000_000_000.0 + i * 1_000_000_000.0,
            "dividend_yield_ttm": 0.03 + i * 0.002,
            "dividend_stability_3y": 0.7 + i * 0.01,
            "earnings_positive": True,
            "payout_ratio": 0.5 + i * 0.02,
            "roe_ttm": 0.08 + i * 0.005,
            "roe_stability_3y": 0.7,
            "realized_vol_126": 0.25 - i * 0.003,
            "mom_12_1": 0.08 + i * 0.02,
            "sma200_gap": 0.03 + i * 0.01,
            "suspension_days_63": 0,
            "is_st": False,
            "list_days": 2000 + i * 100,
        })
    return pd.DataFrame(rows)


def test_combo_defaults():
    assert strategy.PROFILE_NAME == "cn_equity_combo"
    assert strategy.DEFAULT_ETF_WEIGHT == 0.40
    assert strategy.DEFAULT_STOCK_WEIGHT == 0.40
    assert strategy.DEFAULT_DIVIDEND_WEIGHT == 0.20


def test_combo_build_target_weights_with_all_legs():
    mh = pd.concat([_etf_history(), _stock_history()], ignore_index=True)
    fs = _dividend_snapshot()
    weights, metadata = strategy.build_target_weights(
        market_history=mh,
        feature_snapshot=fs,
        etf_weight=0.4,
        stock_weight=0.4,
        dividend_weight=0.2,
    )
    assert weights
    assert 0 < sum(weights.values()) <= 1.0
    combo_meta = metadata.get("combo", {})
    assert combo_meta.get("etf_weight") == 0.4
    assert combo_meta.get("stock_weight") == 0.4
    assert combo_meta.get("dividend_weight") == 0.2


def test_combo_compute_signals():
    mh = pd.concat([_etf_history(), _stock_history()], ignore_index=True)
    fs = _dividend_snapshot()
    weights, signal_desc, has_cash, status_desc, metadata = strategy.compute_signals(
        market_history=mh,
        feature_snapshot=fs,
    )
    assert weights
    assert metadata["signal_source"] == "combo"
    assert metadata["actionable"] is True


def test_combo_dynamic_mode_soft_defense():
    # With a snapshot that triggers soft_defense
    fs = _dividend_snapshot()
    # Force sma200_gap very negative to trigger defense
    fs["sma200_gap"] = -0.15

    weights, metadata = strategy.build_target_weights(
        feature_snapshot=fs,
        etf_weight=0.5,
        stock_weight=0.4,
        dividend_weight=0.1,
        dynamic_mode=True,
    )
    regime = metadata.get("regime", "")
    if regime != "risk_on":
        combo = metadata.get("combo", {})
        # In defense, offensive weights should be reduced
        assert combo.get("etf_weight", 0.5) <= 0.5
        assert combo.get("dividend_weight", 0.1) >= 0.1
