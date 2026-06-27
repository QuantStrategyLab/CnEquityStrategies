from __future__ import annotations

import pandas as pd
import pytest

from quant_platform_kit.strategy_contracts import StrategyContext

from cn_equity_strategies import get_strategy_entrypoint
from cn_equity_strategies.catalog import CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_UNIVERSE_SYMBOLS,
    NASDAQ_ETF_SYMBOL,
    NEW_ENERGY_ETF_SYMBOL,
    SEMICONDUCTOR_ETF_SYMBOL,
    extract_managed_symbols,
)


def _index_etf_rotation_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rates = {
        "510300": 1.0002,
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


def test_index_etf_rotation_entrypoint_returns_volatility_targeted_weight_targets():
    entrypoint = get_strategy_entrypoint(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE)

    decision = entrypoint.evaluate(
        StrategyContext(
            as_of="2026-02-25",
            market_data={"market_history": _index_etf_rotation_history()},
            runtime_config={"min_history_days": 220},
        )
    )

    weights = {position.symbol: position.target_weight for position in decision.positions}
    assert set(weights) == {NEW_ENERGY_ETF_SYMBOL, SEMICONDUCTOR_ETF_SYMBOL}
    assert 0.0 < sum(weights.values()) < 1.0
    assert decision.diagnostics["signal_source"] == "daily_market_history"
    assert decision.diagnostics["target_annual_volatility"] == pytest.approx(0.14)
    assert "cash_residual" in decision.risk_flags
    assert set(DEFAULT_UNIVERSE_SYMBOLS).issubset(set(decision.diagnostics["managed_symbols"]))
