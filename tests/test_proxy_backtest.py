from __future__ import annotations

import math

import pandas as pd
import pytest

from cn_equity_strategies.backtest.proxy_simulator import (
    ProxyBacktestConfig,
    compute_backtest_metrics,
    run_proxy_backtest,
)
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


@pytest.mark.parametrize("returns, expected", [([-0.1], -0.1), ([-0.1, -0.1], -0.19), ([0.1, -0.2], -0.2)])
def test_metrics_drawdown_includes_initial_equity_without_extra_observation(returns, expected):
    metrics = compute_backtest_metrics(pd.Series(returns))
    assert metrics["max_drawdown"] == pytest.approx(expected)
    assert metrics["days"] == len(returns)


@pytest.mark.parametrize("returns", [[0.1, -0.1], [0.01, 0.02, -0.01]])
def test_metrics_sharpe_uses_annualized_arithmetic_mean(returns):
    mean = math.fsum(returns) / len(returns)
    daily_std = math.sqrt(math.fsum((value - mean) ** 2 for value in returns) / len(returns))
    metrics = compute_backtest_metrics(pd.Series(returns))
    assert metrics["sharpe_ratio"] == pytest.approx(mean / daily_std * math.sqrt(252))


@pytest.mark.parametrize("returns", [[], [0.0], [0.1, 0.1]])
def test_metrics_empty_and_zero_volatility_sharpe_remain_zero(returns):
    assert compute_backtest_metrics(pd.Series(returns, dtype=float))["sharpe_ratio"] == 0.0


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 0.0, -1.0])
@pytest.mark.parametrize("missing_day", ["2024-01-03", "2024-01-04"])
def test_proxy_rejects_missing_held_or_execution_price(value, missing_day):
    rows = [{"date": day, "symbol": symbol, "close": 10.0}
            for day in pd.bdate_range("2024-01-02", periods=5)
            for symbol in ("510300", "510500")]
    for row in rows:
        if row["date"] == pd.Timestamp(missing_day) and row["symbol"] == "510300":
            row["close"] = value
    if value is None:
        rows = [row for row in rows if row["close"] is not None]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly"))


def test_proxy_ignores_unheld_missing_price_without_dropping_valuation_days():
    rows = [{"date": day, "symbol": symbol, "close": 10.0}
            for day in pd.bdate_range("2024-01-02", periods=5)
            for symbol in ("510300", "510500")
            if not (day == pd.Timestamp("2024-01-04") and symbol == "510500")]
    result = run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                               config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly", commission_rate=0,
                                                         min_commission=0, cash_reserve_ratio=0))
    assert len(result.equity_curve) == 5
    assert result.daily_returns.eq(0).all()
    assert result.final_holdings["510300"] > 0


def test_proxy_does_not_drop_all_nan_held_valuation_day():
    rows = [{"date": day, "symbol": "510300", "close": float("nan") if i == 2 else 10.0}
            for i, day in enumerate(pd.bdate_range("2024-01-02", periods=5))]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly"))


def test_proxy_rejects_whole_missing_trading_day_while_holding():
    rows = [{"date": day, "symbol": "510300", "close": 10.0}
            for day in pd.bdate_range("2024-01-02", periods=5)
            if day != pd.Timestamp("2024-01-04")]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly"))


def test_proxy_does_not_require_quotes_on_calendar_holidays():
    rows = [{"date": day, "symbol": "510300", "close": 10.0}
            for day in pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"])]
    result = run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                               config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly"))
    assert len(result.equity_curve) == 4
    assert result.final_holdings["510300"] > 0


def test_proxy_all_cash_tolerates_missing_trading_day_without_inventing_holdings():
    rows = [{"date": day, "symbol": "510300", "close": 10.0}
            for day in pd.bdate_range("2024-01-02", periods=5)
            if day != pd.Timestamp("2024-01-04")]
    result = run_proxy_backtest(pd.DataFrame(rows), lambda history: ({}, {}),
                               config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="biweekly"))
    assert len(result.equity_curve) == 5
    assert not result.final_holdings
    assert result.daily_returns.eq(0).all()
