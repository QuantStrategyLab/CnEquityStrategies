#!/usr/bin/env python3
"""P3.5: proxy backtest for cn_dividend_quality_snapshot using monthly factor panels."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PIPELINE_SRC = ROOT.parent / "CnEquitySnapshotPipelines" / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, PIPELINE_SRC, QPK_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    ProxyBacktestResult,
    compute_backtest_metrics,
)
from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_strategy  # noqa: E402
from cn_equity_strategies.strategies.etf_rotation_core import normalize_symbol  # noqa: E402
from cn_equity_snapshot_pipelines.akshare_enrichment import (  # noqa: E402
    FACTOR_SNAPSHOT_COLUMNS,
    compute_dividend_stability,
    compute_financial_features,
    compute_price_features,
    extract_fhps_features,
    merge_factor_row,
    normalize_symbol as pipeline_normalize_symbol,
    stamp_as_of,
)
from cn_equity_snapshot_pipelines.akshare_metadata import (  # noqa: E402
    build_symbol_sector_map,
    lookup_sector,
)
from cn_equity_snapshot_pipelines.akshare_staging import (  # noqa: E402
    DEFAULT_STAGING_SYMBOLS,
    resolve_universe_symbols,
)
from quant_platform_kit.common.cn_equity_calendar import (  # noqa: E402
    add_cn_equity_trading_days,
    is_cn_equity_trading_day,
)

SAFE_HAVEN = dividend_strategy.SAFE_HAVEN
DEFAULT_UNIVERSE = tuple(dict.fromkeys([*DEFAULT_STAGING_SYMBOLS, SAFE_HAVEN]))


def resolve_research_universe(
    ak: Any,
    fhps_table: pd.DataFrame,
    *,
    universe_mode: str = "staging",
    expanded_top_n: int = 40,
    custom_symbols: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    stock_symbols = resolve_universe_symbols(
        ak,
        fhps_table,
        mode=universe_mode,
        custom_symbols=custom_symbols,
        expanded_top_n=expanded_top_n,
    )
    return tuple(dict.fromkeys([*stock_symbols, SAFE_HAVEN]))


@dataclass(frozen=True)
class SnapshotProxyBacktestConfig:
    initial_cash: float = 1_000_000.0
    lot_size: int = 100
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    limit_pct: float = 0.10
    cash_reserve_ratio: float = 0.02
    min_history_days: int = 252


def _month_end_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    normalized = pd.Series(index).dt.normalize()
    grouped = normalized.groupby([normalized.dt.year, normalized.dt.month]).max()
    output: list[pd.Timestamp] = []
    for value in grouped.sort_index():
        day = pd.Timestamp(value).date()
        if is_cn_equity_trading_day(day):
            output.append(pd.Timestamp(value))
    return output


def _slice_hist(hist: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    frame = hist.copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.normalize()
    return frame.loc[frame["日期"] <= as_of.normalize()]


def _slice_financials(financials: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if financials.empty:
        return financials
    frame = financials.copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.normalize()
    return frame.loc[frame["日期"] <= as_of.normalize()]


def _slice_dividends(dividends: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if dividends.empty:
        return dividends
    frame = dividends.copy()
    date_column = "除权除息日" if "除权除息日" in frame.columns else "股权登记日"
    frame["event_date"] = pd.to_datetime(frame[date_column], errors="coerce").dt.normalize()
    return frame.loc[frame["event_date"] <= as_of.normalize()]


def _fetch_stock_history(ak: Any, symbol: str, *, start: str, end: str) -> pd.DataFrame:
    return ak.stock_zh_a_hist(
        symbol=pipeline_normalize_symbol(symbol),
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )


def _fetch_etf_history(ak: Any, symbol: str, *, start: str, end: str) -> pd.DataFrame:
    frame = ak.fund_etf_hist_em(
        symbol=pipeline_normalize_symbol(symbol),
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    if frame.empty:
        return frame
    output = frame.rename(columns={"日期": "日期", "收盘": "收盘", "成交额": "成交额", "成交量": "成交量"})
    return output


def _fetch_fhps_table(ak: Any) -> pd.DataFrame:
    from cn_equity_snapshot_pipelines.akshare_enrichment import FHPS_CANDIDATE_DATES

    last_error: Exception | None = None
    for report_date in FHPS_CANDIDATE_DATES:
        try:
            frame = ak.stock_fhps_em(date=report_date)
            if frame is not None and not frame.empty:
                frame = frame.copy()
                frame["symbol"] = frame["代码"].map(pipeline_normalize_symbol)
                return frame
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("stock_fhps_em returned no data")


def _build_factor_row_as_of(
    symbol: str,
    as_of: pd.Timestamp,
    *,
    ak: Any,
    fhps_table: pd.DataFrame,
    stock_hist: pd.DataFrame,
    financials: pd.DataFrame,
    dividends: pd.DataFrame,
    sector: str,
) -> dict[str, object]:
    normalized = pipeline_normalize_symbol(symbol)
    hist_slice = _slice_hist(stock_hist, as_of)
    if hist_slice.empty:
        raise ValueError(f"no price history for {normalized} as of {as_of.date()}")
    price = compute_price_features(hist_slice, as_of=as_of.date())
    financial_slice = _slice_financials(financials, as_of)
    financial_features = compute_financial_features(financial_slice)
    dividend_stability_3y = compute_dividend_stability(_slice_dividends(dividends, as_of))

    fhps_features = None
    if not fhps_table.empty:
        matched = fhps_table.loc[fhps_table["symbol"] == normalized]
        if not matched.empty:
            fhps_features = extract_fhps_features(matched.iloc[0], close_cny=float(price["close_cny"]))

    return merge_factor_row(
        symbol=normalized,
        price=price,
        fhps=fhps_features,
        financials=financial_features,
        dividend_stability_3y=dividend_stability_3y,
        sector=sector,
    )


def _safe_haven_factor_row(as_of: pd.Timestamp, etf_hist: pd.DataFrame) -> dict[str, object]:
    hist_slice = _slice_hist(etf_hist, as_of)
    if hist_slice.empty:
        raise ValueError(f"no ETF history for {SAFE_HAVEN} as of {as_of.date()}")
    price = compute_price_features(hist_slice, as_of=as_of.date())
    return {
        "symbol": SAFE_HAVEN,
        "sector": "benchmark",
        "close_cny": float(price["close_cny"]),
        "adv20_cny": float(price["adv20_cny"]),
        "market_cap_cny": 0.0,
        "dividend_yield_ttm": 0.0,
        "dividend_stability_3y": 0.0,
        "earnings_positive": True,
        "payout_ratio": 0.0,
        "roe_ttm": 0.0,
        "roe_stability_3y": 0.0,
        "realized_vol_126": float(price["realized_vol_126"]),
        "mom_12_1": float(price["mom_12_1"]),
        "sma200_gap": float(price["sma200_gap"]),
        "suspension_days_63": int(price["suspension_days_63"]),
        "is_st": False,
        "list_days": int(price["list_days"]),
    }


def _symbol_has_price_at(hist: pd.DataFrame, as_of: pd.Timestamp, *, min_rows: int = 20) -> bool:
    sliced = _slice_hist(hist, as_of)
    return len(sliced) >= int(min_rows)


def _active_stock_symbols_as_of(
    stock_symbols: tuple[str, ...],
    stock_histories: Mapping[str, pd.DataFrame],
    as_of: pd.Timestamp,
    *,
    min_rows: int = 20,
) -> tuple[str, ...]:
    output: list[str] = []
    for symbol in stock_symbols:
        normalized = pipeline_normalize_symbol(symbol)
        hist = stock_histories.get(normalized)
        if hist is None or hist.empty:
            continue
        if _symbol_has_price_at(hist, as_of, min_rows=min_rows):
            output.append(normalized)
    return tuple(output)


def _build_close_matrix(
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


def _day_prices(close: pd.DataFrame, day_ts: pd.Timestamp) -> dict[str, float]:
    prices: dict[str, float] = {}
    if day_ts not in close.index:
        return prices
    row = close.loc[day_ts]
    for symbol, value in row.items():
        if pd.notna(value) and float(value) > 0:
            prices[str(symbol)] = float(value)
    return prices


def build_monthly_factor_panel(
    *,
    symbols: tuple[str, ...] | None = None,
    start: str,
    end: str,
    universe_mode: str = "staging",
    expanded_top_n: int = 40,
    custom_symbols: tuple[str, ...] | None = None,
    refresh_sector_map: bool = False,
    sector_map: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    import akshare as ak

    fhps_table = _fetch_fhps_table(ak)
    if symbols is None:
        symbols = resolve_research_universe(
            ak,
            fhps_table,
            universe_mode=universe_mode,
            expanded_top_n=expanded_top_n,
            custom_symbols=custom_symbols,
        )

    stock_symbols = tuple(symbol for symbol in symbols if symbol != SAFE_HAVEN)
    diagnostics: dict[str, object] = {
        "symbols": list(symbols),
        "universe_mode": universe_mode,
        "errors": {},
    }

    if sector_map is None:
        sector_map = build_symbol_sector_map(ak, force_refresh=refresh_sector_map)
    diagnostics["sector_map_size"] = int(len(sector_map))

    stock_histories: dict[str, pd.DataFrame] = {}
    financials_map: dict[str, pd.DataFrame] = {}
    dividends_map: dict[str, pd.DataFrame] = {}
    for symbol in stock_symbols:
        normalized = pipeline_normalize_symbol(symbol)
        try:
            stock_histories[normalized] = _fetch_stock_history(ak, normalized, start=start, end=end)
            financials_map[normalized] = ak.stock_financial_analysis_indicator(
                symbol=normalized,
                start_year=str(pd.Timestamp(start).year - 4),
            )
            dividends_map[normalized] = ak.stock_history_dividend_detail(symbol=normalized, indicator="分红")
        except Exception as exc:
            diagnostics["errors"][normalized] = str(exc)

    etf_hist = _fetch_etf_history(ak, SAFE_HAVEN, start=start, end=end)
    if etf_hist.empty:
        raise ValueError(f"failed to download ETF history for {SAFE_HAVEN}")

    etf_dates = pd.to_datetime(etf_hist["日期"], errors="coerce").dropna().dt.normalize().sort_values().unique()
    trading_index = pd.DatetimeIndex(etf_dates)
    month_ends = _month_end_rebalance_dates(trading_index)
    month_ends = [day for day in month_ends if pd.Timestamp(start) <= day <= pd.Timestamp(end)]

    min_panel_history_rows = 20
    active_counts: list[int] = []
    rows: list[dict[str, object]] = []
    for as_of in month_ends:
        active_symbols = _active_stock_symbols_as_of(
            stock_symbols,
            stock_histories,
            as_of,
            min_rows=min_panel_history_rows,
        )
        active_counts.append(len(active_symbols))
        month_rows: list[dict[str, object]] = []
        for normalized in active_symbols:
            hist = stock_histories.get(normalized)
            if hist is None or hist.empty:
                continue
            try:
                month_rows.append(
                    _build_factor_row_as_of(
                        normalized,
                        as_of,
                        ak=ak,
                        fhps_table=fhps_table,
                        stock_hist=hist,
                        financials=financials_map.get(normalized, pd.DataFrame()),
                        dividends=dividends_map.get(normalized, pd.DataFrame()),
                        sector=lookup_sector(normalized, sector_map),
                    )
                )
            except Exception as exc:
                diagnostics.setdefault("month_errors", {})[f"{normalized}@{as_of.date()}"] = str(exc)
        if not month_rows:
            continue
        try:
            month_rows.append(_safe_haven_factor_row(as_of, etf_hist))
        except Exception as exc:
            diagnostics.setdefault("month_errors", {})[f"{SAFE_HAVEN}@{as_of.date()}"] = str(exc)
            continue
        stamped = stamp_as_of(pd.DataFrame(month_rows, columns=list(FACTOR_SNAPSHOT_COLUMNS)), as_of=as_of.date().isoformat())
        rows.extend(stamped.to_dict(orient="records"))

    if not rows:
        raise ValueError("factor panel is empty; check AkShare downloads and date range")

    panel = pd.DataFrame(rows)
    panel["as_of"] = pd.to_datetime(panel["as_of"], errors="coerce").dt.normalize()
    diagnostics["month_count"] = int(panel["as_of"].nunique())
    diagnostics["row_count"] = int(len(panel))
    diagnostics["avg_active_symbols_per_month"] = (
        float(sum(active_counts) / len(active_counts)) if active_counts else 0.0
    )
    diagnostics["min_active_symbols_per_month"] = int(min(active_counts)) if active_counts else 0
    return panel, diagnostics


def build_market_history_from_downloads(
    *,
    symbols: tuple[str, ...],
    start: str,
    end: str,
) -> pd.DataFrame:
    import akshare as ak

    rows: list[dict[str, object]] = []
    for symbol in symbols:
        normalized = pipeline_normalize_symbol(symbol)
        if normalized == SAFE_HAVEN:
            hist = _fetch_etf_history(ak, normalized, start=start, end=end)
        else:
            hist = _fetch_stock_history(ak, normalized, start=start, end=end)
        if hist.empty:
            continue
        for item in hist.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": normalized,
                    "close": float(getattr(item, "收盘")),
                }
            )
    output = pd.DataFrame(rows)
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def run_snapshot_proxy_backtest(
    factor_panel: pd.DataFrame,
    market_history: pd.DataFrame,
    *,
    config: SnapshotProxyBacktestConfig | None = None,
    strategy_kwargs: Mapping[str, Any] | None = None,
) -> ProxyBacktestResult:
    settings = config or SnapshotProxyBacktestConfig()
    kwargs = dict(strategy_kwargs or {})
    panel = factor_panel.copy()
    panel["as_of"] = pd.to_datetime(panel["as_of"], errors="coerce").dt.normalize()
    snapshots_by_day = {
        pd.Timestamp(day): frame.drop(columns=["as_of"])
        for day, frame in panel.groupby("as_of", sort=True)
    }

    symbols = tuple(dict.fromkeys(market_history["symbol"].map(normalize_symbol).tolist()))
    close = _build_close_matrix(market_history, symbols=symbols)
    if len(close) < int(settings.min_history_days):
        raise ValueError(f"market_history requires at least {settings.min_history_days} overlapping trading days")

    index = pd.DatetimeIndex(close.index)
    rebalance_dates = _month_end_rebalance_dates(index)
    current_holdings: set[str] = set()

    cash = float(settings.initial_cash)
    holdings: dict[str, int] = {}
    pending_targets: dict[str, float] | None = None
    pending_signal_day: pd.Timestamp | None = None
    pending_metadata: dict[str, object] = {}
    rebalance_events: list[dict[str, object]] = []
    equity_points: dict[pd.Timestamp, float] = {}

    def _portfolio_value(prices: Mapping[str, float]) -> float:
        equity = float(cash)
        for symbol, quantity in holdings.items():
            price = prices.get(symbol)
            if price is None or quantity <= 0:
                continue
            equity += float(quantity) * float(price)
        return equity

    def _commission(notional: float) -> float:
        if notional <= 0.0:
            return 0.0
        return max(float(notional) * float(settings.commission_rate), float(settings.min_commission))

    def _round_lot(shares: float) -> int:
        if shares <= 0.0:
            return 0
        return int(shares // int(settings.lot_size)) * int(settings.lot_size)

    for day in index:
        day_ts = pd.Timestamp(day)
        prices = _day_prices(close, day_ts)
        prev_day_pos = index.get_loc(day_ts) - 1
        prev_prices = _day_prices(close, pd.Timestamp(index[prev_day_pos])) if prev_day_pos >= 0 else prices

        execution_due = False
        if pending_targets is not None and pending_signal_day is not None:
            execution_day = pd.Timestamp(add_cn_equity_trading_days(pending_signal_day.date(), 1))
            execution_due = day_ts >= execution_day

        if execution_due and pending_targets is not None:
            portfolio_value = _portfolio_value(prices)
            investable = portfolio_value * (1.0 - float(settings.cash_reserve_ratio))
            target_values = {
                normalize_symbol(symbol): investable * float(weight)
                for symbol, weight in pending_targets.items()
                if float(weight) > 0.0
            }
            all_symbols = sorted(set(holdings) | set(target_values) | set(close.columns))
            for symbol in all_symbols:
                price = prices.get(symbol)
                if price is None or price <= 0:
                    continue
                prev_price = prev_prices.get(symbol, price)
                limit_status = "normal"
                if prev_price > 0:
                    change = price / prev_price - 1.0
                    if change >= float(settings.limit_pct) - 1e-9:
                        limit_status = "limit_up"
                    elif change <= -float(settings.limit_pct) + 1e-9:
                        limit_status = "limit_down"

                current_qty = int(holdings.get(symbol, 0))
                target_qty = _round_lot(target_values.get(symbol, 0.0) / price) if symbol in target_values else 0
                delta = target_qty - current_qty
                if delta < 0 and limit_status == "limit_down":
                    continue
                if delta > 0 and limit_status == "limit_up":
                    continue
                if delta < 0:
                    sell_qty = min(current_qty, -delta)
                    notional = sell_qty * price
                    fee = _commission(notional)
                    cash += notional - fee
                    holdings[symbol] = current_qty - sell_qty
                elif delta > 0:
                    buy_qty = delta
                    notional = buy_qty * price
                    fee = _commission(notional)
                    total_cost = notional + fee
                    if total_cost > cash:
                        affordable = _round_lot(max(cash - fee, 0.0) / price)
                        buy_qty = affordable
                        notional = buy_qty * price
                        fee = _commission(notional)
                        total_cost = notional + fee
                    if buy_qty <= 0:
                        continue
                    cash -= total_cost
                    holdings[symbol] = current_qty + buy_qty

            current_holdings.clear()
            current_holdings.update(symbol for symbol, qty in holdings.items() if qty > 0)
            rebalance_events.append(
                {
                    "signal_date": pending_signal_day.date().isoformat() if pending_signal_day else None,
                    "execution_date": day_ts.date().isoformat(),
                    "targets": dict(pending_targets),
                    "metadata": dict(pending_metadata),
                    "portfolio_value_after": _portfolio_value(prices),
                }
            )
            pending_targets = None
            pending_signal_day = None
            pending_metadata = {}

        if day_ts in rebalance_dates and day_ts >= index[int(settings.min_history_days) - 1]:
            snapshot = snapshots_by_day.get(day_ts)
            if snapshot is None:
                prior_days = [candidate for candidate in snapshots_by_day if candidate <= day_ts]
                if prior_days:
                    snapshot = snapshots_by_day[max(prior_days)]
            if snapshot is not None and not snapshot.empty:
                weights, _ranked, metadata = dividend_strategy.build_target_weights(
                    snapshot,
                    current_holdings=current_holdings,
                    **kwargs,
                )
                pending_targets = {normalize_symbol(symbol): float(value) for symbol, value in weights.items()}
                pending_signal_day = day_ts
                pending_metadata = dict(metadata)

        equity_points[day_ts] = _portfolio_value(prices)

    equity_curve = pd.Series(equity_points).sort_index()
    daily_returns = equity_curve.pct_change().fillna(0.0)
    metrics = compute_backtest_metrics(daily_returns)
    return ProxyBacktestResult(
        equity_curve=equity_curve,
        daily_returns=daily_returns,
        rebalance_events=rebalance_events,
        metrics=metrics,
        final_holdings=dict(holdings),
        final_cash=cash,
    )


def _benchmark_buy_hold(market_history: pd.DataFrame, *, symbol: str = SAFE_HAVEN) -> ProxyBacktestResult:
    def signal_fn(_history: Any, **_kwargs: Any):
        return {symbol: 1.0}, {"label": symbol}

    from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest

    return run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(min_history_days=252),
        universe_symbols=(symbol,),
    )


def _metrics_slice(daily_returns: pd.Series, start: str, end: str) -> dict[str, float | int]:
    series = daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if series.empty:
        return {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + series).cumprod()
    years = len(series) / 252.0
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "days": int(len(series)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": annual_return,
        "max_drawdown": float(drawdown.min()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="P3.5 proxy backtest for cn_dividend_quality_snapshot.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--holdings-count", type=int, default=4)
    parser.add_argument(
        "--universe-mode",
        choices=("staging", "expanded", "custom"),
        default="staging",
        help="staging=8-symbol default; expanded=fhps dividend-yield pool; custom=use --symbols",
    )
    parser.add_argument("--expanded-top-n", type=int, default=40)
    parser.add_argument("--refresh-sector-map", action="store_true")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_STAGING_SYMBOLS),
        help="Used when --universe-mode=custom (510300 is appended automatically)",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    custom_symbols: tuple[str, ...] | None = None
    if args.universe_mode == "custom":
        custom_symbols = tuple(
            dict.fromkeys(
                pipeline_normalize_symbol(item)
                for item in args.symbols.split(",")
                if pipeline_normalize_symbol(item)
            )
        )

    strategy_kwargs = {
        "holdings_count": int(args.holdings_count),
    }

    panel, panel_diag = build_monthly_factor_panel(
        start=args.start,
        end=args.end,
        universe_mode=args.universe_mode,
        expanded_top_n=args.expanded_top_n,
        custom_symbols=custom_symbols,
        refresh_sector_map=args.refresh_sector_map,
    )
    universe = tuple(panel_diag["symbols"])
    market_history = build_market_history_from_downloads(
        symbols=universe,
        start=args.start,
        end=args.end,
    )

    strategy = run_snapshot_proxy_backtest(
        panel,
        market_history,
        strategy_kwargs=strategy_kwargs,
    )
    benchmark = _benchmark_buy_hold(market_history, symbol=SAFE_HAVEN)

    periods = {
        "full": (args.start, args.end),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_2026": ("2023-01-01", args.end),
    }
    output = {
        "profile": dividend_strategy.PROFILE_NAME,
        "start": args.start,
        "end": args.end,
        "universe": list(universe),
        "universe_mode": args.universe_mode,
        "panel_diagnostics": panel_diag,
        "strategy_full": strategy.metrics,
        "benchmark_510300_full": benchmark.metrics,
        "periods": {
            key: {
                "dividend_quality": _metrics_slice(strategy.daily_returns, pstart, pend),
                "benchmark_510300": _metrics_slice(benchmark.daily_returns, pstart, pend),
            }
            for key, (pstart, pend) in periods.items()
        },
        "limitations": [
            f"universe_mode={args.universe_mode}; expanded pool uses fhps dividend-yield filter, not full A-share",
            "fhps table uses latest available report table, not fully point-in-time report selection",
            "proxy uses 510300 calendar + per-symbol ffill; monthly panel filters symbols with price history at as_of",
            "evidence gate only; not promotion-ready without PIT fhps and live data validation",
        ],
    }

    print("\n========== P3.5 cn_dividend_quality_snapshot proxy ==========")
    print(
        f"universe: {len(universe)} symbols ({args.universe_mode}) | "
        f"months: {panel_diag.get('month_count')}"
    )
    sm = output["strategy_full"]
    bm = output["benchmark_510300_full"]
    print(
        f"dividend_quality ann={sm['annual_return']:.2%} total={sm['total_return']:.2%} "
        f"mdd={sm['max_drawdown']:.2%} rebalances={len(strategy.rebalance_events)}"
    )
    print(
        f"510300 B&H    ann={bm['annual_return']:.2%} total={bm['total_return']:.2%} "
        f"mdd={bm['max_drawdown']:.2%}"
    )
    for key, row in output["periods"].items():
        dq = row["dividend_quality"]
        bb = row["benchmark_510300"]
        if dq["days"] <= 0:
            continue
        print(
            f"  {key:<10} dq={dq['total_return']:+7.2%} (ann {dq['annual_return']:6.2%}) | "
            f"510300={bb['total_return']:+7.2%} (ann {bb['annual_return']:6.2%})"
        )

    if args.json_output:
        args.json_output.write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
