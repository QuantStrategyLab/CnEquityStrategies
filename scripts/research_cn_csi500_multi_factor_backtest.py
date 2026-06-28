#!/usr/bin/env python3
"""Proxy backtest for cn_csi500_multi_factor_snapshot — monthly factor panel + proxy simulation.

Usage:
    python scripts/research_cn_csi500_multi_factor_backtest.py
    python scripts/research_cn_csi500_multi_factor_backtest.py \\
        --json-output docs/research/cn_csi500_multi_factor_backtest_20260628.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PIPELINE_SRC = ROOT.parent / "CnEquitySnapshotPipelines" / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, PIPELINE_SRC, QPK_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import akshare as ak
from cn_equity_strategies.strategies import cn_csi500_multi_factor_snapshot as strategy
from cn_equity_strategies.backtest.proxy_simulator import compute_backtest_metrics
from cn_equity_snapshot_pipelines.akshare_enrichment import normalize_symbol as pipe_normalize
from cn_equity_snapshot_pipelines.akshare_metadata import build_symbol_sector_map, lookup_sector

CSI500_CODE = "000905"
SAFE_HAVEN = strategy.SAFE_HAVEN
MOM_6_1_DAYS = 126  # ~6 months
MOM_12_1_DAYS = 252
REBALANCE_FREQUENCY = "monthly"
MIN_HISTORY_DAYS = 252
MAXDD_WINDOW = 126


def _month_end_dates(start: str, end: str) -> list[pd.Timestamp]:
    from quant_platform_kit.common.cn_equity_calendar import is_cn_equity_trading_day
    all_days = pd.bdate_range(start, end, freq="B")
    months = all_days.to_series().groupby(all_days.month).max()
    valid = []
    for d in months:
        ts = pd.Timestamp(d).normalize()
        if is_cn_equity_trading_day(ts.date()):
            valid.append(ts)
    return valid


def _fetch_stock_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    return ak.stock_zh_a_hist(symbol=pipe_normalize(symbol), period="daily",
                              start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")


def _fetch_etf_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    frame = ak.fund_etf_hist_em(symbol=pipe_normalize(symbol), period="daily",
                                start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")
    if frame.empty:
        return frame
    frame["symbol"] = pipe_normalize(symbol)
    return frame


def _compute_maxdd_126(close_series: pd.Series) -> float:
    if len(close_series) < 2:
        return 0.0
    rolling = close_series.tail(MAXDD_WINDOW)
    dd = (rolling / rolling.cummax() - 1.0).min()
    return float(dd)


def build_factor_panel(
    stock_symbols: tuple[str, ...],
    sector_map: dict[str, str],
    *,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    diagnostics: dict[str, object] = {"errors": {}, "symbols": list(stock_symbols)}
    hist_map: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(stock_symbols):
        norm = pipe_normalize(symbol)
        try:
            hist = _fetch_stock_history(norm, start, end)
            if not hist.empty:
                hist_map[norm] = hist
        except Exception as e:
            diagnostics["errors"][norm] = str(e)

    # Fetch 510300 for benchmark comparison
    bench_hist = _fetch_etf_history(SAFE_HAVEN, start, end)
    if bench_hist.empty:
        raise ValueError("failed to fetch benchmark ETF history")

    etf_dates = pd.to_datetime(bench_hist["日期"], errors="coerce").dropna().dt.normalize().sort_values()
    month_ends = _month_end_dates(start, end)
    month_ends = [d for d in month_ends if etf_dates.min() <= d <= etf_dates.max()]

    panel_rows: list[dict[str, object]] = []
    active_counts: list[int] = []
    for as_of in month_ends:
        as_of_ts = pd.Timestamp(as_of).normalize()
        month_rows: list[dict[str, object]] = []
        active_this_month = 0
        for norm, hist in hist_map.items():
            dates = pd.to_datetime(hist["日期"], errors="coerce").dropna().dt.normalize()
            hist_before = hist.loc[dates <= as_of_ts]
            if len(hist_before) < MIN_HISTORY_DAYS:
                continue
            active_this_month += 1

            close = pd.to_numeric(hist_before["收盘"], errors="coerce").dropna()
            if len(close) < 20:
                continue
            latest_close = float(close.iloc[-1])
            turnover = pd.to_numeric(hist_before["成交额"], errors="coerce")
            adv20 = float(turnover.tail(20).mean()) if turnover.tail(20).notna().any() else 0.0
            mkt_cap = float(close.iloc[-1]) * 1_000_000_000  # rough estimate if not available
            roe_raw = pd.to_numeric(hist_before.get("净资产报酬率(%)", pd.Series(dtype=float)), errors="coerce")
            roe_ttm = float(roe_raw.dropna().iloc[-1] / 100.0) if not roe_raw.dropna().empty else 0.0
            eps_raw = pd.to_numeric(hist_before.get("摊薄每股收益(元)", pd.Series(dtype=float)), errors="coerce")
            earnings_pos = bool(eps_raw.dropna().iloc[-1] > 0.0) if not eps_raw.dropna().empty else False

            returns = close.pct_change().dropna()
            mom_6 = float(close.pct_change(MOM_6_1_DAYS).dropna().iloc[-1]) if len(close) > MOM_6_1_DAYS else 0.0
            mom_12 = float(close.pct_change(MOM_12_1_DAYS).dropna().iloc[-1]) if len(close) > MOM_12_1_DAYS else 0.0
            vol_126 = float(returns.tail(MAXDD_WINDOW).std(ddof=0) * (252 ** 0.5)) if len(returns) >= MAXDD_WINDOW else 0.0
            maxdd = _compute_maxdd_126(close) if len(close) >= MAXDD_WINDOW else 0.0
            sma200 = float(close.iloc[-1] / close.tail(200).mean() - 1.0) if len(close) >= 200 else 0.0

            # Relative momentum vs CSI300 benchmark
            bench_slice = bench_hist.loc[pd.to_datetime(bench_hist["日期"], errors="coerce").dt.normalize() <= as_of_ts]
            bench_close = pd.to_numeric(bench_slice["收盘"], errors="coerce").dropna()
            rel_mom = 0.0
            if len(close) > MOM_6_1_DAYS and len(bench_close) > MOM_6_1_DAYS:
                stock_mom_6 = close.iloc[-1] / close.iloc[-MOM_6_1_DAYS] - 1.0
                bench_mom_6 = bench_close.iloc[-1] / bench_close.iloc[-MOM_6_1_DAYS] - 1.0
                rel_mom = float(stock_mom_6 - bench_mom_6)

            sector = lookup_sector(norm, sector_map)
            month_rows.append({
                "symbol": norm,
                "sector": sector,
                "close": latest_close,
                "adv20_cny": max(adv20, 1.0),
                "market_cap_cny": mkt_cap,
                "roe_ttm": roe_ttm,
                "earnings_positive": earnings_pos,
                "mom_6_1": mom_6,
                "mom_12_1": mom_12,
                "rel_mom_6m_vs_benchmark": rel_mom,
                "sma200_gap": sma200,
                "realized_vol_126": max(vol_126, 0.01),
                "maxdd_126": maxdd,
                "eligible": True,
            })

        # Add safe haven row
        bench_close_latest = pd.to_numeric(bench_hist["收盘"], errors="coerce").dropna()
        if not bench_close_latest.empty:
            bench_value = float(bench_close_latest.iloc[-1])
            month_rows.append({
                "symbol": SAFE_HAVEN,
                "sector": "benchmark",
                "close": bench_value,
                "adv20_cny": 1_000_000_000,
                "market_cap_cny": 0.0,
                "roe_ttm": 0.0,
                "earnings_positive": True,
                "mom_6_1": 0.0,
                "mom_12_1": 0.0,
                "rel_mom_6m_vs_benchmark": 0.0,
                "sma200_gap": 0.0,
                "realized_vol_126": 0.20,
                "maxdd_126": 0.0,
                "eligible": True,
            })

        if month_rows:
            active_counts.append(active_this_month)
            df = pd.DataFrame(month_rows)
            df["as_of"] = as_of_ts.date().isoformat()
            panel_rows.extend(df.to_dict(orient="records"))

    if not panel_rows:
        raise ValueError("empty factor panel — check data downloads and date range")

    panel = pd.DataFrame(panel_rows)
    diagnostics["month_count"] = int(panel["as_of"].nunique())
    diagnostics["row_count"] = int(len(panel))
    diagnostics["avg_active"] = float(sum(active_counts) / len(active_counts)) if active_counts else 0
    return panel, diagnostics


def build_market_history(
    stock_symbols: tuple[str, ...],
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    # ETF benchmark
    etf = _fetch_etf_history(SAFE_HAVEN, start, end)
    if not etf.empty:
        for _, r in etf.iterrows():
            rows.append({"date": r["日期"], "symbol": SAFE_HAVEN, "close": float(r["收盘"])})
    # Stocks
    for symbol in stock_symbols:
        norm = pipe_normalize(symbol)
        try:
            hist = _fetch_stock_history(norm, start, end)
        except Exception:
            continue
        for _, r in hist.iterrows():
            rows.append({"date": r["日期"], "symbol": norm, "close": float(r["收盘"])})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    return df.sort_values(["date", "symbol"]).reset_index(drop=True)


def _metrics_slice(daily_returns: pd.Series, start: str, end: str) -> dict[str, float | int]:
    series = daily_returns.loc[pd.Timestamp(start): pd.Timestamp(end)].dropna()
    if series.empty:
        return {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + series).cumprod()
    years = len(series) / 252.0
    ann = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    dd = float((equity / equity.cummax() - 1.0).min())
    return {"days": int(len(series)), "total_return": float(equity.iloc[-1] - 1.0), "annual_return": ann, "max_drawdown": dd}


def main() -> None:
    parser = argparse.ArgumentParser(description="CSI500 multi-factor snapshot proxy backtest.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--max-symbols", type=int, default=100, help="Limit CSI500 download for speed")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    print("Fetching CSI500 constituents...")
    csi500 = ak.index_stock_cons_csindex(CSI500_CODE)
    all_symbols = tuple(csi500["成分券代码"].astype(str).str.zfill(6).tolist())
    if args.max_symbols:
        all_symbols = all_symbols[:args.max_symbols]
    print(f"  {len(all_symbols)} symbols")

    print("Building sector map...")
    sector_map = build_symbol_sector_map(ak, force_refresh=False)
    if not sector_map:
        sector_map = build_symbol_sector_map(ak, force_refresh=True)
    print(f"  {len(sector_map)} sectors")

    print("Building factor panel...")
    panel, panel_diag = build_factor_panel(all_symbols, sector_map, start=args.start, end=args.end)
    print(f"  {panel_diag.get('month_count')} months, {panel_diag.get('row_count')} rows, avg active={panel_diag.get('avg_active')}")

    universe_symbols = tuple(dict.fromkeys([*all_symbols, SAFE_HAVEN]))
    print("Building market history...")
    market_history = build_market_history(universe_symbols, start=args.start, end=args.end)
    print(f"  {len(market_history)} rows")

    # Build snapshot map per month and run custom daily simulation
    from cn_equity_strategies.backtest.dividend_snapshot_proxy_helpers import build_close_matrix, day_prices
    from quant_platform_kit.common.cn_equity_calendar import add_cn_equity_trading_days

    panel["as_of"] = pd.to_datetime(panel["as_of"], errors="coerce").dt.normalize()
    snapshots = {d: g.drop(columns=["as_of"]) for d, g in panel.groupby("as_of", sort=True)}

    close = build_close_matrix(market_history, symbols=universe_symbols, calendar_symbol=SAFE_HAVEN)
    index = pd.DatetimeIndex(close.index)
    rebalance_dates = _month_end_dates(args.start, args.end)

    cash = 1_000_000.0
    holdings: dict[str, int] = {}
    current_holdings_set: set[str] = set()
    pending_targets: dict[str, float] | None = None
    pending_signal_day: pd.Timestamp | None = None
    rebalance_events: list[dict[str, object]] = []
    equity_curve: dict[pd.Timestamp, float] = {}
    lot_size = 100
    commission_rate = 0.0003
    min_commission = 5.0
    cash_reserve_ratio = 0.02

    def portfolio_value(prices: dict[str, float]) -> float:
        val = cash
        for sym, qty in holdings.items():
            p = prices.get(sym)
            if p and qty > 0:
                val += qty * p
        return val

    def commission(notional: float) -> float:
        return max(notional * commission_rate, min_commission) if notional > 0 else 0.0

    def round_lot(shares: float) -> int:
        return int(shares // lot_size) * lot_size if shares > 0 else 0

    for i, day in enumerate(index):
        day_ts = pd.Timestamp(day)
        prices = day_prices(close, day_ts)

        # Execute pending trades
        if pending_targets is not None and pending_signal_day is not None:
            exec_day = pd.Timestamp(add_cn_equity_trading_days(pending_signal_day.date(), 1))
            if day_ts >= exec_day:
                pv = portfolio_value(prices)
                investable = pv * (1.0 - cash_reserve_ratio)
                target_values = {s: investable * w for s, w in pending_targets.items() if w > 0}
                for sym in sorted(set(list(holdings) + list(target_values) + list(close.columns))):
                    price = prices.get(sym)
                    if not price or price <= 0:
                        continue
                    cur_qty = holdings.get(sym, 0)
                    tgt_qty = round_lot(target_values.get(sym, 0.0) / price) if sym in target_values else 0
                    delta = tgt_qty - cur_qty
                    if delta < 0:
                        notional = -delta * price
                        cash += notional - commission(notional)
                        holdings[sym] = cur_qty + delta
                    elif delta > 0:
                        notional = delta * price
                        fee = commission(notional)
                        if notional + fee > cash:
                            affordable = round_lot(max(cash - fee, 0.0) / price)
                            delta = affordable - cur_qty
                            notional = delta * price if delta > 0 else 0.0
                            fee = commission(notional) if notional > 0 else 0.0
                        if delta > 0:
                            cash -= notional + fee
                            holdings[sym] = cur_qty + delta
                current_holdings_set = {s for s, q in holdings.items() if q > 0}
                rebalance_events.append({"signal_date": str(pending_signal_day.date()), "execution_date": str(day_ts.date()), "targets": dict(pending_targets)})
                pending_targets = None
                pending_signal_day = None

        # On rebalance date, generate signal
        if day_ts in rebalance_dates and day_ts >= index[MIN_HISTORY_DAYS - 1]:
            snapshot = snapshots.get(day_ts, None)
            if snapshot is None:
                prior = [d for d in snapshots if d <= day_ts]
                if prior:
                    snapshot = snapshots[max(prior)]
            if snapshot is not None and not snapshot.empty:
                weights, _ranked, metadata = strategy.build_target_weights(
                    snapshot, current_holdings=current_holdings_set,
                )
                pending_targets = weights
                pending_signal_day = day_ts

        equity_curve[day_ts] = portfolio_value(prices)

    daily_returns = pd.Series(equity_curve).sort_index().pct_change().fillna(0.0)
    full_metrics = compute_backtest_metrics(daily_returns)

    print("\n========== CSI500 Multi-Factor Snapshot Proxy ==========")
    print(f"Panel: {panel_diag.get('month_count')} months, avg {panel_diag.get('avg_active')} active/month")
    print(f"Strategy: ann={full_metrics['annual_return']:.2%} total={full_metrics['total_return']:.2%} mdd={full_metrics['max_drawdown']:.2%} sharpe={full_metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Rebalances: {len(rebalance_events)}")

    output = {
        "profile": strategy.PROFILE_NAME,
        "start": args.start, "end": args.end,
        "panel_diagnostics": panel_diag,
        "strategy_metrics": full_metrics,
        "periods": {
            key: _metrics_slice(daily_returns, pstart, pend)
            for key, (pstart, pend) in [("full", (args.start, args.end)), ("bear_2021_2022", ("2021-01-01", "2022-12-31")), ("oos_2024_2026", ("2024-01-01", args.end))]
        },
        "rebalance_count": len(rebalance_events),
    }
    print("\nPeriod breakdown:")
    for k, v in output["periods"].items():
        print(f"  {k:15s} ann={v['annual_return']:6.2%} total={v['total_return']:+.2%} mdd={v['max_drawdown']:7.2%}")

    if args.json_output:
        serializable = json.loads(json.dumps(output, default=str))
        args.json_output.write_text(json.dumps(serializable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
