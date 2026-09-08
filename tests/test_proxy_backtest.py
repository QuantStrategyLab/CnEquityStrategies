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


def _valuation_dates():
    # Dec 28 warms up the Dec 29 signal; Jan 2 is the first execution.
    return pd.to_datetime(["2023-12-28", "2023-12-29", *pd.bdate_range("2024-01-02", periods=5)])


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 0.0, -1.0])
@pytest.mark.parametrize("missing_day", ["2024-01-02", "2024-01-03"])
def test_proxy_rejects_missing_held_or_execution_price(value, missing_day):
    rows = [{"date": day, "symbol": symbol, "close": 10.0}
            for day in _valuation_dates()
            for symbol in ("510300", "510500")]
    for row in rows:
        if row["date"] == pd.Timestamp(missing_day) and row["symbol"] == "510300":
            row["close"] = value
    if value is None:
        rows = [row for row in rows if row["close"] is not None]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="monthly"))


def test_proxy_ignores_unheld_missing_price_without_dropping_valuation_days():
    rows = [{"date": day, "symbol": symbol, "close": 10.0}
            for day in _valuation_dates()
            for symbol in ("510300", "510500")
            if not (day == pd.Timestamp("2024-01-04") and symbol == "510500")]
    result = run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                               config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="monthly", commission_rate=0,
                                                         min_commission=0, cash_reserve_ratio=0))
    assert len(result.equity_curve) == len(_valuation_dates())
    assert result.daily_returns.eq(0).all()
    assert result.final_holdings["510300"] > 0


def test_proxy_does_not_drop_all_nan_held_valuation_day():
    rows = [{"date": day, "symbol": "510300", "close": float("nan") if day == pd.Timestamp("2024-01-04") else 10.0}
            for day in _valuation_dates()]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="monthly"))


def test_proxy_rejects_whole_missing_trading_day_while_holding():
    rows = [{"date": day, "symbol": "510300", "close": 10.0}
            for day in _valuation_dates()
            if day != pd.Timestamp("2024-01-04")]
    with pytest.raises(ValueError, match="finite positive price"):
        run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                           config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="monthly"))


def test_proxy_does_not_require_quotes_on_calendar_holidays():
    rows = [{"date": day, "symbol": "510300", "close": 10.0}
            for day in pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"])]
    result = run_proxy_backtest(pd.DataFrame(rows), lambda history: ({"510300": 1.0}, {}),
                               config=ProxyBacktestConfig(min_history_days=1, rebalance_frequency="monthly"))
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


def test_proxy_waits_for_complete_visible_warmup_at_month_end():
    from datetime import date

    from quant_platform_kit.common.cn_equity_calendar import is_cn_equity_trading_day
    from cn_equity_strategies.backtest.orchestrator_runner import _slice_history

    history = pd.DataFrame([
        {"date": day, "symbol": symbol, "close": 10.0}
        for day in pd.date_range("2024-01-02", "2025-02-06")
        if is_cn_equity_trading_day(day.date())
        for symbol in ("510300", "510500")
    ])
    history = _slice_history(
        history, start_date=date(2025, 1, 9), end_date=date(2025, 2, 6), lookback_days=225,
    )
    visible_dates = []

    def signal(visible_history):
        days = pd.DatetimeIndex(visible_history["date"].unique())
        assert len(days) >= 220
        visible_dates.append(days)
        return {"510300": 1.0}, {}

    result = run_proxy_backtest(
        history, signal, universe_symbols=("510300", "510500"),
        config=ProxyBacktestConfig(min_history_days=220),
    )

    assert visible_dates
    assert visible_dates[0].max() == pd.Timestamp("2025-01-24")
    assert len(result.rebalance_events) == 1
    event = result.rebalance_events[0]
    assert event["signal_date"] == "2025-01-27"
    assert event["execution_date"] == "2025-02-05"
    assert result.equity_curve.loc[:"2025-02-04"].eq(1_000_000.0).all()


@pytest.mark.parametrize("start, expected_events", [("2024-01-26", 1), ("2024-01-29", 0)])
def test_proxy_warmup_boundary_uses_only_prior_observations(start, expected_events):
    history = pd.DataFrame([
        {"date": day, "symbol": "510300", "close": 10.0}
        for day in pd.bdate_range(start, "2024-02-01")
    ])

    def signal(visible_history):
        assert visible_history["date"].nunique() >= 3
        return {"510300": 1.0}, {}

    result = run_proxy_backtest(
        history, signal, universe_symbols=("510300",),
        config=ProxyBacktestConfig(min_history_days=3),
    )

    assert len(result.rebalance_events) == expected_events
    if expected_events:
        assert result.rebalance_events[0]["signal_date"] == "2024-01-31"
        assert result.rebalance_events[0]["execution_date"] == "2024-02-01"


def test_proxy_cash_round_trip_preserves_cash_and_both_commissions():
    history = pd.DataFrame([
        {"date": day, "symbol": "510300", "close": 10.0}
        for day in pd.bdate_range("2024-01-02", periods=23)
    ])
    calls = 0

    def signal(visible_history):
        nonlocal calls
        calls += 1
        return ({"510300": 1.0} if calls == 1 else {}), {}

    result = run_proxy_backtest(
        history, signal, universe_symbols=("510300",),
        config=ProxyBacktestConfig(
            initial_cash=10_000.0, min_history_days=1, rebalance_frequency="biweekly",
            commission_rate=0.0003, min_commission=5.0, cash_reserve_ratio=0.02,
        ),
    )

    trades = [trade for event in result.rebalance_events for trade in event["trades"]]
    assert [(trade["side"], trade["qty"], trade["fee"]) for trade in trades] == [
        ("buy", 900, 5.0), ("sell", 900, 5.0),
    ]
    assert result.final_holdings == {}
    assert result.final_cash == pytest.approx(9_990.0)
    assert result.equity_curve.iloc[-1] == pytest.approx(result.final_cash)
    assert (1.0 + result.daily_returns).prod() == pytest.approx(0.999)
