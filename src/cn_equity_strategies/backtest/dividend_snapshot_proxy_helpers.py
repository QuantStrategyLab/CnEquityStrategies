from __future__ import annotations

from collections.abc import Callable, Mapping

import pandas as pd

from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_strategy
from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol

SAFE_HAVEN = dividend_strategy.SAFE_HAVEN


def slice_hist(hist: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    frame = hist.copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.normalize()
    return frame.loc[frame["日期"] <= as_of.normalize()]


def symbol_has_price_at(hist: pd.DataFrame, as_of: pd.Timestamp, *, min_rows: int = 20) -> bool:
    sliced = slice_hist(hist, as_of)
    return len(sliced) >= int(min_rows)


def active_stock_symbols_as_of(
    stock_symbols: tuple[str, ...],
    stock_histories: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    *,
    min_rows: int = 20,
    normalize: Callable[[str], str] = normalize_symbol,
) -> tuple[str, ...]:
    output: list[str] = []
    for symbol in stock_symbols:
        normalized = normalize(symbol)
        hist = stock_histories.get(normalized)
        if hist is None or hist.empty:
            continue
        if symbol_has_price_at(hist, as_of, min_rows=min_rows):
            output.append(normalized)
    return tuple(output)


def build_close_matrix(
    market_history: pd.DataFrame,
    *,
    symbols: tuple[str, ...],
    calendar_symbol: str = SAFE_HAVEN,
) -> pd.DataFrame:
    """Build wide close matrix; calendar follows ``calendar_symbol`` without requiring all names each day."""
    frame = market_history.copy()
    frame["symbol"] = frame["symbol"].map(normalize_symbol)
    close = (
        frame.loc[frame["symbol"].isin(symbols)]
        .pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
        .sort_index()
    )
    ordered = [symbol for symbol in symbols if symbol in close.columns]
    if not ordered:
        raise ValueError("market_history has no requested symbols")
    close = close.loc[:, ordered].ffill()
    anchor = calendar_symbol if calendar_symbol in close.columns else ordered[0]
    close = close.loc[close[anchor].notna() & (close[anchor] > 0)]
    if close.empty:
        raise ValueError(f"market_history has no trading days for calendar symbol {anchor}")
    return close


def day_prices(close: pd.DataFrame, day_ts: pd.Timestamp) -> dict[str, float]:
    prices: dict[str, float] = {}
    if day_ts not in close.index:
        return prices
    row = close.loc[day_ts]
    for symbol, value in row.items():
        if pd.notna(value) and float(value) > 0:
            prices[str(symbol)] = float(value)
    return prices
