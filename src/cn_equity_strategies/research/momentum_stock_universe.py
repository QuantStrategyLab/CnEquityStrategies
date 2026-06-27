from __future__ import annotations

from typing import Literal

import pandas as pd

from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol

MomentumUniverseMode = Literal["csi500", "csi1000", "liquid_top"]

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
    if mode == "csi500":
        return fetch_index_constituents(CSI500_INDEX_CODE)
    if mode == "csi1000":
        return fetch_index_constituents(CSI1000_INDEX_CODE)
    if mode == "liquid_top":
        return fetch_liquid_top_symbols(top_n=liquid_top_n)
    raise ValueError(f"unsupported momentum universe mode: {mode!r}")
