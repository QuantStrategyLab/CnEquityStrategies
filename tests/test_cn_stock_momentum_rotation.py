from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies import cn_stock_momentum_rotation as strategy


def _stock_history(*, symbols: tuple[str, ...], periods: int = 320) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    rows = []
    for symbol_idx, symbol in enumerate(symbols):
        price = 10.0 + symbol_idx * 3.0
        daily_rate = 1.0015 + symbol_idx * 0.0002
        for idx, date in enumerate(dates):
            noise = 1.0 + 0.002 * ((idx + symbol_idx) % 5 - 2)
            price *= daily_rate * noise
            rows.append({"date": date, "symbol": symbol, "close": price, "volume": 1_000_000.0 + symbol_idx})
    return pd.DataFrame(rows)


def test_stock_momentum_rotation_defaults():
    assert strategy.PROFILE_NAME == "cn_stock_momentum_rotation"
    assert strategy.CN_EQUITY_DOMAIN == "cn_equity"
    assert strategy.SIGNAL_SOURCE == "daily_market_history"
    assert strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY == 0.25
    assert strategy.DEFAULT_ENABLE_BENCHMARK_RISK_OFF is True
    assert strategy.DEFAULT_BENCHMARK_SYMBOL == "510300"
    assert strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS == 120
    assert strategy.DEFAULT_TOP_N == 5
    assert strategy.DEFAULT_DEFENSIVE_SYMBOLS == ("510300",)


def test_stock_momentum_rotation_compute_signals():
    symbols = tuple(f"{idx:06d}" for idx in range(1, 15)) + ("510300",)
    history = _stock_history(symbols=symbols)

    weights, signal_desc, has_cash, status_desc, metadata = strategy.compute_signals(
        history,
        universe_symbols=tuple(f"{idx:06d}" for idx in range(1, 15)),
        defensive_symbols=("510300",),
        benchmark_symbol="510300",
        enable_benchmark_risk_off=True,
        benchmark_trend_window_days=120,
        top_n=5,
        min_history_days=220,
        target_annual_volatility=0.25,
        max_pair_correlation=1.0,
    )
    assert weights
    assert 0 < sum(weights.values()) <= 1.0
    assert "signal_description" not in metadata
    assert metadata["signal_source"] == "daily_market_history"
    assert metadata["status_icon"] == "🇨🇳"
    assert metadata["actionable"] is True
    assert metadata["profile_variant"] == "stock_momentum_rotation"


def test_stock_momentum_rotation_compute_latest_signal():
    symbols = tuple(f"{idx:06d}" for idx in range(1, 15)) + ("510300",)
    history = _stock_history(symbols=symbols)

    signal = strategy.compute_latest_signal(
        history,
        universe_symbols=tuple(f"{idx:06d}" for idx in range(1, 15)),
        defensive_symbols=("510300",),
        benchmark_symbol="510300",
        enable_benchmark_risk_off=True,
        benchmark_trend_window_days=120,
        top_n=5,
        min_history_days=220,
        target_annual_volatility=0.25,
        max_pair_correlation=1.0,
    )
    assert "as_of" in signal
    assert "weights" in signal
    assert "ranking" in signal
    assert "signal_state" in signal
    assert signal["target_annual_volatility"] == 0.25
