from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, Sequence

import pandas as pd

from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol

MomentumUniverseMode = Literal["csi500", "csi1000", "csi500_pit", "liquid_top"]

CSI500_INDEX_CODE = "000905"
CSI1000_INDEX_CODE = "000852"
DEFAULT_LIQUID_TOP_N = 300


def _normalize_constituent_code(value: object) -> str:
    return normalize_symbol(str(value).strip())


def fetch_index_constituents(index_code: str) -> tuple[str, ...]:
    import akshare as ak

    frame = ak.index_stock_cons_csindex(symbol=str(index_code))
    if frame is None or frame.empty:
        raise RuntimeError(f"index_stock_cons_csindex returned no data for {index_code}")
    column = "成分券代码"
    if column not in frame.columns:
        raise RuntimeError(f"missing {column} in index constituents for {index_code}")
    symbols = tuple(
        dict.fromkeys(_normalize_constituent_code(value) for value in frame[column].tolist() if str(value).strip())
    )
    if not symbols:
        raise RuntimeError(f"no symbols parsed for index {index_code}")
    return symbols


@lru_cache(maxsize=8)
def _load_index_inclusion_table(index_code: str) -> pd.DataFrame:
    import akshare as ak

    frame = ak.index_stock_cons(symbol=str(index_code))
    if frame is None or frame.empty:
        raise RuntimeError(f"index_stock_cons returned no data for {index_code}")
    date_column = "纳入日期"
    code_column = "品种代码"
    if date_column not in frame.columns or code_column not in frame.columns:
        raise RuntimeError(f"missing inclusion columns in index_stock_cons for {index_code}")
    working = frame.copy()
    working["symbol"] = working[code_column].map(_normalize_constituent_code)
    working["inclusion_date"] = pd.to_datetime(working[date_column], errors="coerce")
    working = working.loc[working["symbol"].astype(str).str.len() > 0]
    working = working.loc[working["inclusion_date"].notna()]
    if working.empty:
        raise RuntimeError(f"no parsable inclusion rows for index {index_code}")
    return working[["symbol", "inclusion_date"]].drop_duplicates(subset=["symbol"], keep="last")


def index_constituents_as_of(index_code: str, as_of: str) -> tuple[str, ...]:
    """Point-in-time filter using published inclusion dates (current members only).

    Tries the accumulated membership timeline from CnEquitySnapshotPipelines
    first. Falls back to inclusion-date PIT filtering when the timeline does
    not cover the requested date.

    Removed historical members are not recovered via the inclusion-date
    fallback. Inclusion dates reflect the latest index entry event in
    ``index_stock_cons``; use history-based grandfathering in
    ``filter_offensive_for_pit`` when rebalance-time prices extend well
    before that date.
    """
    # Try membership timeline first
    try:
        from cn_equity_snapshot_pipelines.index_membership import (
            constituents_as_of as _membership_as_of,
        )

        members = _membership_as_of(str(index_code), as_of, fallback_to_inclusion_table=False)
        if members:
            return members
    except (ImportError, RuntimeError):
        pass

    # Fallback: inclusion-date table from akshare
    as_of_ts = pd.Timestamp(as_of).normalize()
    table = _load_index_inclusion_table(str(index_code))
    selected = table.loc[table["inclusion_date"] <= as_of_ts, "symbol"]
    symbols = tuple(dict.fromkeys(str(value) for value in selected.tolist()))
    if not symbols:
        raise RuntimeError(f"no index constituents on or before {as_of} for {index_code}")
    return symbols


def filter_offensive_for_pit(
    offensive: Sequence[str],
    *,
    pit_index_code: str | None,
    as_of: str,
    market_history: Any | None = None,
    min_history_days: int = 220,
) -> tuple[str, ...]:
    if not pit_index_code:
        return tuple(offensive)
    allowed = set(index_constituents_as_of(str(pit_index_code), as_of))
    as_of_ts = pd.Timestamp(as_of).normalize()
    kept: list[str] = []
    history_frame = None
    if market_history is not None:
        from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol

        if isinstance(market_history, pd.DataFrame):
            history_frame = market_history.copy()
        else:
            history_frame = pd.DataFrame(list(market_history))
        history_frame["date"] = pd.to_datetime(history_frame["date"], utc=False).dt.tz_localize(None)
        history_frame["symbol"] = history_frame["symbol"].map(normalize_symbol)

    for symbol in offensive:
        if symbol in allowed:
            kept.append(symbol)
            continue
        if history_frame is None or history_frame.empty:
            continue
        symbol_frame = history_frame.loc[history_frame["symbol"] == symbol].sort_values("date")
        if symbol_frame.empty:
            continue
        first_date = pd.Timestamp(symbol_frame["date"].iloc[0]).normalize()
        rows_before_as_of = symbol_frame.loc[symbol_frame["date"] <= as_of_ts]
        if (
            first_date <= as_of_ts - pd.Timedelta(days=int(min_history_days))
            and len(rows_before_as_of) >= int(min_history_days)
        ):
            kept.append(symbol)
    return tuple(dict.fromkeys(kept)) if kept else tuple(offensive)


def fetch_liquid_top_symbols(*, top_n: int = DEFAULT_LIQUID_TOP_N) -> tuple[str, ...]:
    import akshare as ak

    frame = ak.stock_zh_a_spot_em()
    if frame is None or frame.empty:
        raise RuntimeError("stock_zh_a_spot_em returned no data")
    working = frame.copy()
    working["symbol"] = working["代码"].map(_normalize_constituent_code)
    working["name"] = working["名称"].astype(str)
    working["turnover"] = pd.to_numeric(working["成交额"], errors="coerce")
    working = working.loc[working["turnover"].notna() & (working["turnover"] > 0)]
    working = working.loc[~working["name"].str.contains("ST", case=False, na=False)]
    working = working.sort_values("turnover", ascending=False)
    symbols = tuple(dict.fromkeys(working["symbol"].head(int(top_n)).tolist()))
    if len(symbols) < 50:
        raise RuntimeError(f"liquid_top universe too small: {len(symbols)}")
    return symbols


def resolve_momentum_stock_universe(
    mode: MomentumUniverseMode,
    *,
    liquid_top_n: int = DEFAULT_LIQUID_TOP_N,
) -> tuple[str, ...]:
    if mode in {"csi500", "csi500_pit"}:
        return fetch_index_constituents(CSI500_INDEX_CODE)
    if mode == "csi1000":
        return fetch_index_constituents(CSI1000_INDEX_CODE)
    if mode == "liquid_top":
        return fetch_liquid_top_symbols(top_n=liquid_top_n)
    raise ValueError(f"unsupported momentum universe mode: {mode!r}")
