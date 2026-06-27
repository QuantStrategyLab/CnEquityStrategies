from __future__ import annotations

import pandas as pd
import pytest

from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_TARGET_ANNUAL_VOLATILITY,
    DEFAULT_UNIVERSE_SYMBOLS,
    NASDAQ_ETF_SYMBOL,
    NEW_ENERGY_ETF_SYMBOL,
    SEMICONDUCTOR_ETF_SYMBOL,
    build_target_weights,
    compute_latest_signal,
    extract_managed_symbols,
    normalize_symbol,
)


def _history(*, benchmark_weak: bool = False) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rates = {
        "510300": 0.9995 if benchmark_weak else 1.0002,
        "510500": 1.0001,
        "159915": 0.9998,
        "588000": 1.0000,
        "512100": 1.0003,
        "512170": 1.0004,
        "515030": 1.0009,
        "512760": 1.0008,
        "518880": 1.0005,
        NASDAQ_ETF_SYMBOL: 1.0007,
        "511880": 1.00001,
        "511260": 1.00002,
    }
    rows = []
    for symbol in extract_managed_symbols():
        price = 20.0
        for idx, date in enumerate(dates):
            price *= rates[symbol]
            close = price * (1.0 + 0.04 * ((idx % 5) - 2) / 5)
            rows.append({"date": date, "symbol": symbol, "close": close})
    return pd.DataFrame(rows)


def test_normalize_symbol_accepts_exchange_suffix():
    assert normalize_symbol("510300.SH") == "510300"
    assert normalize_symbol("159915.SZ") == "159915"


def test_index_etf_rotation_selects_top_two_and_applies_volatility_target():
    signal = compute_latest_signal(_history(), min_history_days=220)

    assert signal["signal_state"] == "risk_on"
    assert NEW_ENERGY_ETF_SYMBOL in set(signal["selected_symbols"])
    assert len(signal["selected_symbols"]) <= 2
    assert signal["target_annual_volatility"] == pytest.approx(DEFAULT_TARGET_ANNUAL_VOLATILITY)
    assert signal["realized_portfolio_volatility"] > DEFAULT_TARGET_ANNUAL_VOLATILITY
    assert 0.0 < signal["gross_exposure"] < 1.0
    assert signal["cash_weight"] == pytest.approx(1.0 - signal["gross_exposure"])
    assert signal["benchmark_risk_off"] is False


def test_index_etf_rotation_switches_to_defensive_when_benchmark_risk_off():
    signal = compute_latest_signal(_history(benchmark_weak=True), min_history_days=220)

    assert signal["benchmark_risk_off"] is True
    assert signal["signal_state"] == "defensive"
    assert set(signal["selected_symbols"]).issubset({"511880", "511260"})


def test_index_etf_rotation_can_disable_volatility_target():
    weights, metadata = build_target_weights(
        _history(),
        min_history_days=220,
        target_annual_volatility=None,
    )

    assert NEW_ENERGY_ETF_SYMBOL in set(weights)
    assert len(weights) <= 2
    assert sum(weights.values()) == pytest.approx(1.0)
    assert metadata["target_annual_volatility"] is None
    assert metadata["cash_weight"] == pytest.approx(0.0)


def test_index_etf_rotation_managed_symbols_include_defensive_pool():
    managed = extract_managed_symbols()
    assert set(DEFAULT_UNIVERSE_SYMBOLS).issubset(set(managed))
    assert "511880" in managed
    assert "511260" in managed
