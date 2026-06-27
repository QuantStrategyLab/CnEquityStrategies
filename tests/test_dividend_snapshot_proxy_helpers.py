from __future__ import annotations

import pandas as pd
import pytest

from cn_equity_strategies.backtest.dividend_snapshot_proxy_helpers import (
    SAFE_HAVEN,
    active_stock_symbols_as_of,
    build_close_matrix,
    day_prices,
    symbol_has_price_at,
)


def _history(start: str, periods: int, symbol: str = "600519") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"日期": dates, "收盘": [10.0 + idx for idx in range(periods)]})


def test_build_close_matrix_uses_benchmark_calendar_without_full_overlap():
    dates = pd.bdate_range("2020-01-02", periods=5)
    rows = []
    for day in dates:
        rows.append({"date": day, "symbol": SAFE_HAVEN, "close": 3.0})
    for day in dates[2:]:
        rows.append({"date": day, "symbol": "600519", "close": 100.0})
    history = pd.DataFrame(rows)

    close = build_close_matrix(history, symbols=(SAFE_HAVEN, "600519"))
    assert len(close) == 5
    assert close.loc[dates[0], SAFE_HAVEN] == pytest.approx(3.0)
    assert pd.isna(close.loc[dates[0], "600519"])
    assert close.loc[dates[-1], "600519"] == pytest.approx(100.0)


def test_day_prices_skips_missing_values():
    dates = pd.bdate_range("2020-01-02", periods=3)
    close = pd.DataFrame(
        {
            SAFE_HAVEN: [3.0, 3.1, 3.2],
            "600519": [float("nan"), 100.0, 101.0],
        },
        index=dates,
    )
    prices = day_prices(close, dates[0])
    assert prices == {SAFE_HAVEN: 3.0}
    prices_day2 = day_prices(close, dates[1])
    assert prices_day2[SAFE_HAVEN] == pytest.approx(3.1)
    assert prices_day2["600519"] == pytest.approx(100.0)


def test_active_stock_symbols_as_of_filters_by_listing():
    stock_histories = {
        "600519": _history("2019-01-02", 400),
        "001299": _history("2023-01-03", 200),
    }
    as_of = pd.Timestamp("2021-12-31")
    active = active_stock_symbols_as_of(("600519", "001299"), stock_histories, as_of)
    assert active == ("600519",)
    assert symbol_has_price_at(stock_histories["001299"], as_of) is False
