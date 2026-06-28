from __future__ import annotations

import pandas as pd
import pytest

from cn_equity_strategies.strategies import industry_etf_rotation_core as core


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


def test_industry_rotation_applies_max_single_name_weight_cap():

    symbols = tuple(f"{idx:06d}" for idx in range(1, 8))
    weights, metadata = core.build_target_weights(
        _stock_history(symbols=symbols),
        universe_symbols=symbols,
        defensive_symbols=(),
        enable_benchmark_risk_off=False,
        benchmark_symbol=None,
        top_n=5,
        min_history_days=220,
        target_annual_volatility=None,
        max_pair_correlation=1.0,
        max_single_name_weight=0.10,
    )

    assert weights
    assert max(weights.values()) <= 0.10 + 1e-9
    assert metadata["max_single_name_weight"] == pytest.approx(0.10)
