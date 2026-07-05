#!/usr/bin/env python3
"""Proxy backtest for cn_chinext_growth_momentum_quality_snapshot."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
PIPELINE_SRC = ROOT.parent / "CnEquitySnapshotPipelines" / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, SCRIPTS, PIPELINE_SRC, QPK_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_snapshot_pipelines.akshare_enrichment import (  # noqa: E402
    compute_dividend_stability,
    compute_financial_features,
    compute_price_features,
    extract_fhps_features,
    merge_factor_row,
    normalize_symbol as pipeline_normalize_symbol,
    stamp_as_of,
)
from cn_equity_strategies.backtest.dividend_snapshot_proxy_helpers import active_stock_symbols_as_of, slice_hist  # noqa: E402
from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    ProxyBacktestResult,
    compute_backtest_metrics,
    run_proxy_backtest,
)
from cn_equity_strategies.strategies import cn_chinext_growth_momentum_quality_snapshot as chinext_strategy  # noqa: E402
from cn_equity_strategies.research.momentum_stock_history import download_symbol_histories  # noqa: E402

SAFE_HAVEN = chinext_strategy.SAFE_HAVEN
BENCHMARK_SYMBOL = "510300"
try:
    import research_cn_dividend_quality_snapshot_proxy_backtest as dividend_backtest  # noqa: E402
    from research_cn_dividend_quality_snapshot_proxy_backtest import (  # noqa: E402
        _metrics_slice,
        _month_end_rebalance_dates,
        SnapshotProxyBacktestConfig,
        run_snapshot_proxy_backtest,
    )
except Exception:  # pragma: no cover - fallback if script is executed standalone
    SnapshotProxyBacktestConfig = ProxyBacktestConfig  # type: ignore[assignment]

    def _month_end_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        normalized = pd.Series(index).dt.normalize()
        grouped = normalized.groupby([normalized.dt.year, normalized.dt.month]).max()
        return [pd.Timestamp(value) for value in grouped.sort_index()]

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


def _load_info_table() -> pd.DataFrame:
    import akshare as ak

    frame = ak.stock_info_sz_name_code()
    if frame is None or frame.empty:
        raise RuntimeError("stock_info_sz_name_code returned no data")
    output = frame.copy()
    output["symbol"] = output["A股代码"].map(pipeline_normalize_symbol)
    output["name"] = output["A股简称"].astype(str)
    output["board"] = output["板块"].astype(str)
    output["list_date"] = pd.to_datetime(output["A股上市日期"], errors="coerce").dt.normalize()
    output["free_float_shares"] = pd.to_numeric(output["A股流通股本"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    output["total_shares"] = pd.to_numeric(output["A股总股本"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    return output


def _resolve_chinext_universe(*, start: str, top_n: int = 120) -> tuple[str, ...]:
    frame = _load_info_table()
    start_ts = pd.Timestamp(start).normalize()
    frame = frame.loc[
        (frame["board"] == "创业板")
        & frame["list_date"].notna()
        & (frame["list_date"] <= start_ts)
        & ~frame["name"].str.contains("ST", case=False, na=False)
    ].copy()
    frame = frame.loc[frame["free_float_shares"].notna() & (frame["free_float_shares"] > 0)]
    frame = frame.sort_values(["free_float_shares", "list_date"], ascending=[False, True])
    symbols = tuple(dict.fromkeys(frame["symbol"].head(int(top_n)).tolist()))
    if len(symbols) < 10:
        raise ValueError(f"ChiNext universe too small after filtering: {len(symbols)}")
    return symbols


def _parse_yoy_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce") / 100.0


def _rolling_stability(values: pd.Series, window: int = 12) -> float:
    tail = pd.to_numeric(values, errors="coerce").dropna().tail(window)
    if tail.empty:
        return 0.0
    mean = float(tail.mean())
    if abs(mean) < 1e-9:
        return 0.0
    std = float(tail.std(ddof=0))
    return max(0.0, 1.0 - min(std / abs(mean), 1.0))


def _gross_margin_stability(frame: pd.DataFrame) -> float:
    for column in ("主营业务利润率(%)", "销售净利率(%)", "主营业务成本率(%)"):
        if column in frame.columns:
            series = pd.to_numeric(frame[column], errors="coerce").dropna().tail(12)
            if series.empty:
                continue
            mean = float(series.mean())
            if abs(mean) < 1e-9:
                continue
            std = float(series.std(ddof=0))
            return max(0.0, 1.0 - min(std / abs(mean), 1.0))
    return 0.0


def _financial_features_as_of(financials: pd.DataFrame, *, as_of: pd.Timestamp) -> dict[str, float | bool]:
    if financials.empty:
        return {
            "revenue_yoy": 0.0,
            "profit_yoy": 0.0,
            "revenue_acceleration_2q": 0.0,
            "roe_ttm": 0.0,
            "roe_stability_3y": 0.0,
            "gross_margin_stability_3y": 0.0,
            "earnings_positive": False,
        }
    frame = financials.copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.normalize()
    frame = frame.loc[frame["日期"] <= as_of.normalize()].sort_values("日期")
    if frame.empty:
        return {
            "revenue_yoy": 0.0,
            "profit_yoy": 0.0,
            "revenue_acceleration_2q": 0.0,
            "roe_ttm": 0.0,
            "roe_stability_3y": 0.0,
            "gross_margin_stability_3y": 0.0,
            "earnings_positive": False,
        }
    roe_series = pd.to_numeric(frame.get("净资产报酬率(%)"), errors="coerce") / 100.0
    revenue_series = _parse_yoy_series(frame, "主营业务收入增长率(%)")
    profit_series = _parse_yoy_series(frame, "净利润增长率(%)")
    eps_series = pd.to_numeric(frame.get("摊薄每股收益(元)"), errors="coerce")
    latest_roe = float(roe_series.dropna().iloc[-1]) if not roe_series.dropna().empty else 0.0
    latest_revenue_yoy = float(revenue_series.dropna().iloc[-1]) if not revenue_series.dropna().empty else 0.0
    latest_profit_yoy = float(profit_series.dropna().iloc[-1]) if not profit_series.dropna().empty else 0.0
    prev_revenue_yoy = float(revenue_series.dropna().iloc[-2]) if len(revenue_series.dropna()) >= 2 else latest_revenue_yoy
    latest_eps = float(eps_series.dropna().iloc[-1]) if not eps_series.dropna().empty else 0.0
    return {
        "revenue_yoy": latest_revenue_yoy,
        "profit_yoy": latest_profit_yoy,
        "revenue_acceleration_2q": latest_revenue_yoy - prev_revenue_yoy,
        "roe_ttm": latest_roe,
        "roe_stability_3y": _rolling_stability(roe_series, window=12),
        "gross_margin_stability_3y": _gross_margin_stability(frame),
        "earnings_positive": latest_eps > 0.0,
    }


def _download_history_frame(ak: Any, *, symbol: str, start: str, end: str) -> pd.DataFrame:
    normalized = pipeline_normalize_symbol(symbol)
    market_prefix = "sh" if normalized.startswith(("5", "6", "9")) else "sz"
    fetchers = (
        lambda: ak.stock_zh_a_hist(
            symbol=normalized,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
            timeout=8.0,
        ),
        lambda: ak.stock_zh_a_hist_tx(
            symbol=f"{market_prefix}{normalized}",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
            timeout=8.0,
        ),
    )
    frame = None
    for fetch in fetchers:
        for _ in range(3):
            try:
                frame = fetch()
                if frame is not None and not frame.empty:
                    return frame
            except Exception:
                continue
    return pd.DataFrame()


def _stock_histories(
    ak: Any,
    symbols: tuple[str, ...],
    *,
    start: str,
    end: str,
) -> dict[str, pd.DataFrame]:
    histories: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        normalized = pipeline_normalize_symbol(symbol)
        frame = _download_history_frame(ak, symbol=normalized, start=start, end=end)
        if frame is None or frame.empty:
            continue
        output = frame.copy()
        date_column = "date" if "date" in output.columns else "日期"
        close_column = "close" if "close" in output.columns else "收盘"
        amount_column = "amount" if "amount" in output.columns else "成交额"
        output["日期"] = pd.to_datetime(output[date_column], errors="coerce").dt.normalize()
        output["收盘"] = pd.to_numeric(output[close_column], errors="coerce")
        output["成交额"] = pd.to_numeric(output[amount_column], errors="coerce")
        output["成交量"] = output["成交额"]
        histories[normalized] = output.loc[:, ["日期", "收盘", "成交额", "成交量"]].copy()
    return histories


def _download_etf_history(symbol: str, *, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    normalized = pipeline_normalize_symbol(symbol)
    frame = _download_history_frame(ak, symbol=normalized, start=start, end=end)
    if frame is None or frame.empty:
        raise RuntimeError(f"failed to download history for {symbol}")
    output = frame.copy()
    date_column = "date" if "date" in output.columns else "日期"
    close_column = "close" if "close" in output.columns else "收盘"
    amount_column = "amount" if "amount" in output.columns else "成交额"
    output["日期"] = pd.to_datetime(output[date_column], errors="coerce").dt.normalize()
    output["收盘"] = pd.to_numeric(output[close_column], errors="coerce")
    output["成交额"] = pd.to_numeric(output[amount_column], errors="coerce")
    output["成交量"] = output["成交额"]
    return output.loc[:, [col for col in ("日期", "收盘", "成交额", "成交量") if col in output.columns]]


def _histories_to_market_history(histories: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for symbol, frame in histories.items():
        if frame is None or frame.empty:
            continue
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": pipeline_normalize_symbol(symbol),
                    "close": float(getattr(item, "收盘")),
                }
            )
    market_history = pd.DataFrame(rows)
    if market_history.empty:
        return market_history
    market_history["date"] = pd.to_datetime(market_history["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return market_history.sort_values(["date", "symbol"]).reset_index(drop=True)


def _financials_map(ak: Any, symbols: tuple[str, ...], *, start_year: str) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            frame = _call_with_timeout(
                lambda: ak.stock_financial_analysis_indicator(
                    symbol=pipeline_normalize_symbol(symbol),
                    start_year=start_year,
                ),
                timeout_seconds=8.0,
            )
        except Exception:
            continue
        if frame is None or frame.empty:
            continue
        result[pipeline_normalize_symbol(symbol)] = frame.copy()
    return result


def _call_with_timeout(func: Any, *, timeout_seconds: float) -> Any:
    if timeout_seconds <= 0:
        return func()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=float(timeout_seconds))
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError("operation timed out") from exc


def _build_factor_row_as_of(
    symbol: str,
    as_of: pd.Timestamp,
    *,
    stock_hist: pd.DataFrame,
    financials: pd.DataFrame,
    shares: float,
    sector: str,
    name: str,
) -> dict[str, object]:
    hist_slice = slice_hist(stock_hist, as_of)
    if hist_slice.empty:
        raise ValueError(f"no price history for {symbol} as of {as_of.date()}")
    price = compute_price_features(hist_slice, as_of=as_of.date())
    fin = _financial_features_as_of(financials, as_of=as_of)
    market_cap_cny = float(price["close_cny"]) * float(shares) if shares > 0 else 0.0
    return {
        "symbol": pipeline_normalize_symbol(symbol),
        "sector": sector or "unknown",
        "close_cny": float(price["close_cny"]),
        "adv20_cny": float(price["adv20_cny"]),
        "market_cap_cny": market_cap_cny,
        "revenue_yoy": float(fin["revenue_yoy"]),
        "profit_yoy": float(fin["profit_yoy"]),
        "revenue_acceleration_2q": float(fin["revenue_acceleration_2q"]),
        "roe_ttm": float(fin["roe_ttm"]),
        "roe_stability_3y": float(fin["roe_stability_3y"]),
        "gross_margin_stability_3y": float(fin["gross_margin_stability_3y"]),
        "mom_12_1": float(price["mom_12_1"]),
        "mom_6_1": float(price["mom_12_1"]) if len(hist_slice) < 126 else float(hist_slice["收盘"].iloc[-1] / hist_slice["收盘"].iloc[-63] - 1.0),
        "sma200_gap": float(price["sma200_gap"]),
        "realized_vol_126": float(price["realized_vol_126"]),
        "earnings_positive": bool(fin["earnings_positive"]),
        "suspension_days_63": int(price["suspension_days_63"]),
        "is_st": "ST" in str(name).upper(),
        "list_days": int(price["list_days"]),
    }


def build_monthly_factor_panel(
    *,
    start: str,
    end: str,
    top_n: int = 120,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    import akshare as ak

    info = _load_info_table()
    universe = _resolve_chinext_universe(start=start, top_n=top_n)
    universe_info = info.loc[info["symbol"].isin(universe)].copy()
    shares_map = dict(zip(universe_info["symbol"], universe_info["total_shares"].fillna(universe_info["free_float_shares"])))
    sector_map = dict(zip(universe_info["symbol"], universe_info["board"].fillna("unknown")))
    name_map = dict(zip(universe_info["symbol"], universe_info["name"].fillna("")))

    diagnostics: dict[str, object] = {
        "symbols": list(universe),
        "universe_size": len(universe),
        "errors": {},
    }
    histories = _stock_histories(ak, universe, start=(pd.Timestamp(start) - pd.Timedelta(days=450)).date().isoformat(), end=end)
    financials = _financials_map(ak, universe, start_year=str(pd.Timestamp(start).year - 4))
    safe_haven_hist = _download_etf_history(SAFE_HAVEN, start=start, end=end)
    benchmark_hist = _download_etf_history(BENCHMARK_SYMBOL, start=start, end=end)
    market_history = _histories_to_market_history({**histories, SAFE_HAVEN: safe_haven_hist, BENCHMARK_SYMBOL: benchmark_hist})
    active_counts: list[int] = []
    rows: list[dict[str, object]] = []
    rebalance_dates = _month_end_rebalance_dates(pd.DatetimeIndex(pd.to_datetime(safe_haven_hist["日期"], errors="coerce").dropna()))
    rebalance_dates = [day for day in rebalance_dates if pd.Timestamp(start) <= day <= pd.Timestamp(end)]
    min_panel_history_rows = 220
    for as_of in rebalance_dates:
        active_symbols = active_stock_symbols_as_of(
            universe,
            histories,
            as_of,
            min_rows=min_panel_history_rows,
            normalize=pipeline_normalize_symbol,
        )
        active_counts.append(len(active_symbols))
        month_rows: list[dict[str, object]] = []
        for symbol in active_symbols:
            hist = histories.get(symbol)
            if hist is None or hist.empty:
                continue
            try:
                month_rows.append(
                    _build_factor_row_as_of(
                        symbol,
                        as_of,
                        stock_hist=hist,
                        financials=financials.get(symbol, pd.DataFrame()),
                        shares=float(shares_map.get(symbol, 0.0) or 0.0),
                        sector=str(sector_map.get(symbol, "unknown")),
                        name=str(name_map.get(symbol, "")),
                    )
                )
            except Exception as exc:
                diagnostics.setdefault("month_errors", {})[f"{symbol}@{as_of.date()}"] = str(exc)
        if not month_rows:
            continue
        safe_hist = slice_hist(safe_haven_hist, as_of)
        if not safe_hist.empty:
            safe_price = compute_price_features(safe_hist, as_of=as_of.date())
            month_rows.append(
                {
                    "symbol": SAFE_HAVEN,
                    "sector": "benchmark",
                    "close_cny": float(safe_price["close_cny"]),
                    "adv20_cny": float(safe_price["adv20_cny"]),
                    "market_cap_cny": 0.0,
                    "revenue_yoy": 0.0,
                    "profit_yoy": 0.0,
                    "revenue_acceleration_2q": 0.0,
                    "roe_ttm": 0.0,
                    "roe_stability_3y": 0.0,
                    "gross_margin_stability_3y": 0.0,
                    "mom_12_1": float(safe_price["mom_12_1"]),
                    "mom_6_1": float(safe_price["mom_12_1"]),
                    "sma200_gap": float(safe_price["sma200_gap"]),
                    "realized_vol_126": float(safe_price["realized_vol_126"]),
                    "earnings_positive": True,
                    "suspension_days_63": int(safe_price["suspension_days_63"]),
                    "is_st": False,
                    "list_days": int(safe_price["list_days"]),
                }
            )
        rows.extend(stamp_as_of(pd.DataFrame(month_rows), as_of=as_of.date().isoformat()).to_dict(orient="records"))

    if not rows:
        raise ValueError("factor panel is empty; check AkShare downloads and universe selection")

    panel = pd.DataFrame(rows)
    panel["as_of"] = pd.to_datetime(panel["as_of"], errors="coerce").dt.normalize()
    diagnostics["month_count"] = int(panel["as_of"].nunique())
    diagnostics["row_count"] = int(len(panel))
    diagnostics["avg_active_symbols_per_month"] = float(sum(active_counts) / len(active_counts)) if active_counts else 0.0
    diagnostics["min_active_symbols_per_month"] = int(min(active_counts)) if active_counts else 0
    diagnostics["universe_profile"] = {
        "top_n": int(top_n),
        "start": start,
        "end": end,
        "safe_haven": SAFE_HAVEN,
    }
    return panel, market_history, diagnostics


def run_chinext_growth_momentum_quality_proxy_backtest(
    *,
    start: str,
    end: str,
    top_n: int = 120,
    holdings_count: int = chinext_strategy.DEFAULT_HOLDINGS_COUNT,
) -> dict[str, Any]:
    panel, market_history, panel_diag = build_monthly_factor_panel(start=start, end=end, top_n=top_n)
    symbols = tuple(panel_diag["symbols"])

    original_build_target_weights = dividend_backtest.dividend_strategy.build_target_weights
    dividend_backtest.dividend_strategy.build_target_weights = chinext_strategy.build_target_weights
    try:
        result = run_snapshot_proxy_backtest(
            panel,
            market_history,
            strategy_kwargs={"holdings_count": int(holdings_count), "safe_haven": SAFE_HAVEN},
        )
    finally:
        dividend_backtest.dividend_strategy.build_target_weights = original_build_target_weights
    benchmark = run_proxy_backtest(
        market_history.loc[market_history["symbol"] == BENCHMARK_SYMBOL].copy(),
        lambda _h, **_k: ({BENCHMARK_SYMBOL: 1.0}, {"label": BENCHMARK_SYMBOL}),
        config=ProxyBacktestConfig(min_history_days=252),
        universe_symbols=(BENCHMARK_SYMBOL,),
    )
    full = result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    periods = {
        "full": (start, end),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_2026": ("2023-01-01", end),
        "2024_2026": ("2024-01-01", end),
    }
    payload = {
        "start": start,
        "end": end,
        "track": "chinext_growth_momentum_quality",
        "universe": panel_diag["universe_profile"],
        "panel_diagnostics": panel_diag,
        "full_sample": {
            "strategy": compute_backtest_metrics(full),
            "benchmark": compute_backtest_metrics(benchmark.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()),
        },
        "periods": {
            key: {
                "strategy": _metrics_slice(result.daily_returns, pstart, pend),
                "benchmark": _metrics_slice(benchmark.daily_returns, pstart, pend),
            }
            for key, (pstart, pend) in periods.items()
        },
        "limitations": [
            "universe is current ChiNext list filtered by size and ST flags, not historical PIT constituents",
            "financial features come from AkShare quarterly indicators, not a custom PIT financial warehouse",
            "safe-haven fallback uses 159915; compare to 510300 only as a benchmark reference",
        ],
    }
    return payload


def _print_report(payload: dict[str, Any]) -> None:
    strategy = payload["full_sample"]["strategy"]
    benchmark = payload["full_sample"]["benchmark"]
    print("\n=== 创业板成长动量质量 proxy backtest ===\n")
    print(
        f"Universe: top_n={payload['universe']['top_n']} | safe_haven={payload['universe']['safe_haven']} | "
        f"months={payload['panel_diagnostics']['month_count']} | avg_active≈{payload['panel_diagnostics']['avg_active_symbols_per_month']:.1f}"
    )
    print(
        f"Strategy ann={strategy['annual_return']:.2%} total={strategy['total_return']:.2%} "
        f"mdd={strategy['max_drawdown']:.2%} sharpe={strategy['sharpe_ratio']:.2f}"
    )
    print(
        f"Benchmark ann={benchmark['annual_return']:.2%} total={benchmark['total_return']:.2%} "
        f"mdd={benchmark['max_drawdown']:.2%} sharpe={benchmark['sharpe_ratio']:.2f}"
    )
    print("\n分周期:")
    for key, row in payload["periods"].items():
        s = row["strategy"]
        b = row["benchmark"]
        if int(s.get("days", 0)) <= 0:
            continue
        print(
            f"  {key:<10} strategy ann={s['annual_return']:.2%} mdd={s['max_drawdown']:.2%} | "
            f"bench ann={b['annual_return']:.2%} mdd={b['max_drawdown']:.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxy backtest for ChiNext growth momentum quality strategy.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--top-n", type=int, default=120)
    parser.add_argument("--holdings-count", type=int, default=12)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run_chinext_growth_momentum_quality_proxy_backtest(
        start=args.start,
        end=args.end,
        top_n=args.top_n,
        holdings_count=args.holdings_count,
    )
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
