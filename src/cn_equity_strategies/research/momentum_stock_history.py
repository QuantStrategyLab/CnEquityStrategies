from __future__ import annotations

from typing import Iterable

import pandas as pd

from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol

_ETF_SYMBOL_PREFIXES = ("51", "15", "58")
BENCHMARK_SYMBOL = "510300"


def is_etf_symbol(symbol: str) -> bool:
    normalized = normalize_symbol(symbol)
    return normalized.startswith(_ETF_SYMBOL_PREFIXES)


def download_symbol_histories(
    symbols: Iterable[str],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    import akshare as ak

    rows: list[dict[str, object]] = []
    for symbol in dict.fromkeys(normalize_symbol(item) for item in symbols if str(item).strip()):
        try:
            if is_etf_symbol(symbol):
                frame = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""),
                    adjust="qfq",
                )
            else:
                frame = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start.replace("-", ""),
                    end_date=end.replace("-", ""),
                    adjust="qfq",
                )
        except Exception:
            continue
        if frame is None or frame.empty:
            continue
        volume_column = "成交额" if "成交额" in frame.columns else None
        for item in frame.itertuples(index=False):
            row = {
                "date": getattr(item, "日期"),
                "symbol": symbol,
                "close": float(getattr(item, "收盘")),
            }
            if volume_column is not None:
                row["volume"] = float(getattr(item, volume_column))
            rows.append(row)
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def active_stock_symbols_at_start(
    market_history: pd.DataFrame,
    *,
    candidates: tuple[str, ...],
    start: str,
    min_rows: int = 220,
) -> tuple[str, ...]:
    start_ts = pd.Timestamp(start)
    active: list[str] = []
    for symbol in candidates:
        if is_etf_symbol(symbol):
            continue
        frame = market_history.loc[market_history["symbol"] == symbol].sort_values("date")
        if frame.empty:
            continue
        first_date = pd.Timestamp(frame["date"].iloc[0])
        rows_after_start = frame.loc[frame["date"] >= start_ts]
        if first_date <= start_ts + pd.Timedelta(days=120) and len(rows_after_start) >= int(min_rows):
            active.append(symbol)
    return tuple(active)
