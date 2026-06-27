from __future__ import annotations

import pandas as pd
import pytest

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    NASDAQ_ETF_SYMBOL,
    build_target_weights,
    extract_managed_symbols,
)


def _history(*, days: int = 400) -> pd.DataFrame:
    dates = pd.bdate_range("2023-06-01", periods=days)
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


def _signal_fn(history, **kwargs):
    return build_target_weights(history, min_history_days=220, **kwargs)


def test_proxy_backtest_runs_and_produces_positive_equity():
    result = run_proxy_backtest(
        _history(),
        _signal_fn,
        config=ProxyBacktestConfig(initial_cash=1_000_000.0, min_history_days=220),
    )

    assert not result.equity_curve.empty
    assert result.equity_curve.iloc[-1] > 0
    assert result.metrics["days"] > 0
    assert len(result.rebalance_events) >= 1


def test_proxy_backtest_respects_lot_size():
    result = run_proxy_backtest(
        _history(),
        _signal_fn,
        config=ProxyBacktestConfig(lot_size=100, min_history_days=220),
    )

    for event in result.rebalance_events:
        for trade in event["trades"]:
            if trade.get("status") == "filled" and int(trade.get("qty", 0)) > 0:
                assert int(trade["qty"]) % 100 == 0


def test_proxy_backtest_execution_is_after_signal_day():
    result = run_proxy_backtest(
        _history(),
        _signal_fn,
        config=ProxyBacktestConfig(min_history_days=220),
    )

    for event in result.rebalance_events:
        assert event["execution_date"] > event["signal_date"]


def test_proxy_backtest_requires_minimum_history():
    with pytest.raises(ValueError, match="at least 220"):
        run_proxy_backtest(
            _history(days=100),
            _signal_fn,
            config=ProxyBacktestConfig(min_history_days=220),
        )
