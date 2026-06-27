#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

import pandas as pd

from cn_equity_strategies.backtest.proxy_simulator import (
    ProxyBacktestConfig,
    ProxyBacktestResult,
    compute_backtest_metrics,
    run_proxy_backtest,
)
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_rotation
from cn_equity_strategies.strategies import etf_rotation_core as rotation_core
from cn_equity_strategies.strategies import industry_etf_rotation_core as industry_core

# --- A-share staged universes (honest availability; no retroactive inclusion) ---
CN_UNIVERSE_2017 = ("159928", "159915", "512100", "512800")  # all liquid from 2017-01 / 2017-08
CN_UNIVERSE_2019 = (*CN_UNIVERSE_2017, "512690", "512760", "512170")
CN_UNIVERSE_2020 = (*CN_UNIVERSE_2019, "159995", "159819", "159994", "515030")
CN_UNIVERSE_FULL = industry_core.DEFAULT_UNIVERSE_SYMBOLS

CN_BENCHMARK = "510300"

# --- US SPDR sector sleeve (long history, liquid) ---
US_SECTOR_SYMBOLS = (
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLY",
    "XLP",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
)
US_BENCHMARK = "SPY"

LONG_PERIODS: dict[str, tuple[str | None, str | None, tuple[str, ...] | None]] = {
    "full_2017_2026": ("2017-01-01", "2026-06-27", None),
    "phase_2017_2018": ("2017-01-01", "2018-12-31", CN_UNIVERSE_2017),
    "phase_2019_2020": ("2019-01-01", "2020-12-31", CN_UNIVERSE_2019),
    "phase_2021_2022": ("2021-01-01", "2022-12-31", CN_UNIVERSE_FULL),
    "phase_2023_2026": ("2023-01-01", "2026-06-27", CN_UNIVERSE_FULL),
    "bull_2017_2018": ("2017-01-01", "2018-12-31", CN_UNIVERSE_2017),
    "bear_2018_2020": ("2018-01-01", "2020-12-31", CN_UNIVERSE_2017),
    "post_covid_2020_2021": ("2020-01-01", "2021-12-31", CN_UNIVERSE_2020),
    "recent_2021_2026": ("2021-01-01", "2026-06-27", CN_UNIVERSE_FULL),
}


def _metrics_slice(daily_returns: pd.Series, start: str | None, end: str | None) -> dict[str, float | int]:
    series = daily_returns
    if start:
        series = series.loc[pd.Timestamp(start) :]
    if end:
        series = series.loc[: pd.Timestamp(end)]
    series = series.dropna()
    if series.empty:
        return {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0, "annual_volatility": 0.0}
    equity = (1.0 + series).cumprod()
    years = len(series) / 252.0
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "days": int(len(series)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "annual_return": annual_return,
        "max_drawdown": float(drawdown.min()),
        "annual_volatility": float(series.std(ddof=0) * math.sqrt(252)),
    }


def _cn_universe_for_period(start: str, end: str) -> tuple[str, ...]:
    start_ts = pd.Timestamp(start)
    if start_ts >= pd.Timestamp("2021-01-01"):
        return CN_UNIVERSE_FULL
    if start_ts >= pd.Timestamp("2020-01-01"):
        return CN_UNIVERSE_2020
    if start_ts >= pd.Timestamp("2019-01-01"):
        return CN_UNIVERSE_2019
    return CN_UNIVERSE_2017


def _download_cn_history(*, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    symbols = tuple(
        dict.fromkeys(
            [
                *CN_UNIVERSE_FULL,
                CN_BENCHMARK,
                *industry_core.DEFAULT_DEFENSIVE_SYMBOLS,
            ]
        )
    )
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if frame.empty:
            continue
        for item in frame.itertuples(index=False):
            rows.append(
                {
                    "date": getattr(item, "日期"),
                    "symbol": symbol,
                    "close": float(getattr(item, "收盘")),
                    "volume": float(getattr(item, "成交额")),
                }
            )
    output = pd.DataFrame(rows)
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _download_us_history(*, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    symbols = tuple(dict.fromkeys([*US_SECTOR_SYMBOLS, US_BENCHMARK]))
    raw = yf.download(
        list(symbols),
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    rows: list[dict[str, object]] = []
    for symbol in close.columns:
        series = close[symbol].dropna()
        for date, value in series.items():
            rows.append({"date": pd.Timestamp(date).normalize(), "symbol": str(symbol), "close": float(value)})
    output = pd.DataFrame(rows)
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _run_cn_rotation(
    market_history: pd.DataFrame,
    *,
    universe: tuple[str, ...],
    sentiment_mode: Literal["off", "flow", "flow_crowding"] = "off",
) -> ProxyBacktestResult:
    strategy_kwargs = {
        "min_history_days": industry_rotation.DEFAULT_MIN_HISTORY_DAYS,
        "universe_symbols": universe,
        "defensive_symbols": (),
        "sentiment_mode": sentiment_mode,
        "enable_benchmark_risk_off": False,
        "top_n": 5,
        "target_annual_volatility": 0.20,
        "benchmark_symbol": None,
    }

    def signal_fn(history: Any, **kwargs: Any):
        merged = {**kwargs, **strategy_kwargs}
        return industry_rotation.build_target_weights(history, **merged)

    return run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(min_history_days=industry_rotation.DEFAULT_MIN_HISTORY_DAYS),
        universe_symbols=universe,
        strategy_kwargs=strategy_kwargs,
    )


def _window_with_warmup(history: pd.DataFrame, start: str, end: str, *, warmup_days: int = 400) -> pd.DataFrame:
    warmup_start = pd.Timestamp(start) - pd.Timedelta(days=warmup_days)
    return history.loc[(history["date"] >= warmup_start) & (history["date"] <= pd.Timestamp(end))]


def _metrics_from_backtest(backtest: ProxyBacktestResult, start: str, end: str) -> dict[str, float | int]:
    return _metrics_slice(backtest.daily_returns, start, end)


def _run_cn_benchmark(market_history: pd.DataFrame) -> ProxyBacktestResult:
    def signal_fn(_history: Any, **_kwargs: Any):
        return {CN_BENCHMARK: 1.0}, {"label": "510300"}

    return run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(min_history_days=220),
    )


def _us_month_end_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    normalized = pd.Series(index).dt.normalize()
    grouped = normalized.groupby([normalized.dt.year, normalized.dt.month]).max()
    return [pd.Timestamp(value) for value in grouped.sort_index()]


def _run_us_proxy_backtest(
    market_history: pd.DataFrame,
    *,
    universe: tuple[str, ...],
    benchmark: str = US_BENCHMARK,
    top_n: int = 5,
    target_vol: float = 0.20,
) -> ProxyBacktestResult:
    close = rotation_core.build_close_matrix(market_history, universe_symbols=universe)
    if len(close) < 220:
        raise ValueError("insufficient US history")
    index = pd.DatetimeIndex(close.index)
    rebalance_dates = _us_month_end_rebalance_dates(index)

    strategy_kwargs = {
        "min_history_days": 220,
        "universe_symbols": universe,
        "defensive_symbols": (),
        "top_n": top_n,
        "target_annual_volatility": target_vol,
        "benchmark_symbol": None,
    }

    def signal_fn(history: Any, **kwargs: Any):
        merged = {**kwargs, **strategy_kwargs}
        return rotation_core.build_target_weights(history, **merged)

    # Reuse CN proxy path for trade mechanics; US differs (T+0, no limit) but keep next-day execution for parity.
    return run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(
            min_history_days=220,
            lot_size=1,
            limit_pct=1.0,
            commission_rate=0.0003,
            min_commission=1.0,
        ),
        universe_symbols=universe,
        strategy_kwargs=strategy_kwargs,
    )


def _run_us_benchmark(market_history: pd.DataFrame) -> ProxyBacktestResult:
    def signal_fn(_history: Any, **_kwargs: Any):
        return {US_BENCHMARK: 1.0}, {"label": "SPY"}

    return run_proxy_backtest(
        market_history,
        signal_fn,
        config=ProxyBacktestConfig(min_history_days=220, lot_size=1, limit_pct=1.0),
        universe_symbols=(US_BENCHMARK,),
    )


def run_part1_cn_long_horizon(*, start: str, end: str) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    history = _download_cn_history(start=download_start, end=end)

    era_specs = [
        ("era_2017_2018", "2017-01-01", "2018-12-31", CN_UNIVERSE_2017),
        ("era_2019_2020", "2019-01-01", "2020-12-31", CN_UNIVERSE_2019),
        ("era_2021_2026", "2021-01-01", end, CN_UNIVERSE_FULL),
    ]
    era_results: dict[str, Any] = {}
    for key, estart, eend, universe in era_specs:
        window = _window_with_warmup(history, estart, eend)
        rotation = _run_cn_rotation(window, universe=universe, sentiment_mode="off")
        bench = run_proxy_backtest(
            window,
            lambda _h, **_k: ({CN_BENCHMARK: 1.0}, {}),
            config=ProxyBacktestConfig(min_history_days=220),
            universe_symbols=(CN_BENCHMARK,),
        )
        era_results[key] = {
            "start": estart,
            "end": eend,
            "universe": list(universe),
            "industry_rotation": _metrics_from_backtest(rotation, estart, eend),
            "benchmark_510300": _metrics_from_backtest(bench, estart, eend),
        }

    phase_rows: dict[str, Any] = {}
    phase_rotation_returns: dict[str, pd.Series] = {}
    phase_bench_returns: dict[str, pd.Series] = {}
    for key, (pstart, pend, forced_universe) in LONG_PERIODS.items():
        if pstart is None:
            pstart = start
        if pend is None:
            pend = end
        universe = forced_universe or _cn_universe_for_period(pstart, pend)
        window = _window_with_warmup(history, pstart, pend)
        rotation = _run_cn_rotation(window, universe=universe, sentiment_mode="off")
        bench = run_proxy_backtest(
            window,
            lambda _h, **_k: ({CN_BENCHMARK: 1.0}, {}),
            config=ProxyBacktestConfig(min_history_days=220),
            universe_symbols=(CN_BENCHMARK,),
        )
        phase_rotation_returns[key] = rotation.daily_returns.loc[pd.Timestamp(pstart) : pd.Timestamp(pend)]
        phase_bench_returns[key] = bench.daily_returns.loc[pd.Timestamp(pstart) : pd.Timestamp(pend)]
        phase_rows[key] = {
            "universe": list(universe),
            "industry_rotation": _metrics_from_backtest(rotation, pstart, pend),
            "benchmark_510300": _metrics_from_backtest(bench, pstart, pend),
        }

    stitch_keys = ("phase_2017_2018", "phase_2019_2020", "phase_2021_2022", "phase_2023_2026")
    stitched_rotation = pd.concat([phase_rotation_returns[key] for key in stitch_keys]).sort_index()
    stitched_bench = pd.concat([phase_bench_returns[key] for key in stitch_keys]).sort_index()
    era_results["stitched_full_2017_2026"] = {
        "start": start,
        "end": end,
        "universe": [list(LONG_PERIODS[key][2] or ()) for key in stitch_keys],
        "industry_rotation": _metrics_slice(stitched_rotation, start, end),
        "benchmark_510300": _metrics_slice(stitched_bench, start, end),
    }

    return {
        "market": "cn",
        "start": start,
        "end": end,
        "universe_note": "分时代独立池：2017–18 四标的；2019–20 七标的；2021+ 十四标的；stitched 为四段拼接全样本。",
        "eras": era_results,
        "periods": phase_rows,
    }


def run_part2_us_comparison(*, start: str, end: str) -> dict[str, Any]:
    history = _download_us_history(start=start, end=end)
    rotation = _run_us_proxy_backtest(history, universe=US_SECTOR_SYMBOLS)
    benchmark = _run_us_benchmark(history)

    periods = {
        "full": (start, end),
        "2017_2018": ("2017-01-01", "2018-12-31"),
        "2019_2020": ("2019-01-01", "2020-12-31"),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_2026": ("2023-01-01", end),
        "2021_2026": ("2021-01-01", end),
    }
    period_rows = {
        key: {
            "sector_rotation": _metrics_slice(rotation.daily_returns, pstart, pend),
            "benchmark_spy": _metrics_slice(benchmark.daily_returns, pstart, pend),
        }
        for key, (pstart, pend) in periods.items()
    }
    return {
        "market": "us",
        "start": history["date"].min().date().isoformat(),
        "end": history["date"].max().date().isoformat(),
        "universe": list(US_SECTOR_SYMBOLS),
        "rules": "top5, vol20%, monthly, momentum+trend, next-day execution, lot=1, no limit-up/down",
        "sector_rotation_full": rotation.metrics,
        "benchmark_spy_full": benchmark.metrics,
        "periods": period_rows,
    }


def _print_part1(payload: dict[str, Any]) -> None:
    print("\n========== Part 1: A股行业轮动 2017–2026 长样本 ==========")
    print(f"数据: {payload['start']} ~ {payload['end']}")
    print(payload["universe_note"])
    print("\n分时代独立回测（各自用当时可交易池）:")
    for key, row in payload["eras"].items():
        ir = row["industry_rotation"]
        bm = row["benchmark_510300"]
        print(
            f"  {key:<16} {row['start']}~{row['end']} pool={len(row['universe']):2} | "
            f"rotation ann={ir['annual_return']:6.2%} total={ir['total_return']:7.2%} mdd={ir['max_drawdown']:7.2%} | "
            f"510300 ann={bm['annual_return']:6.2%} total={bm['total_return']:7.2%}"
        )
    print("\n分子阶段 total_return:")
    for key, row in payload["periods"].items():
        irp = row["industry_rotation"]
        bmp = row["benchmark_510300"]
        if irp["days"] <= 0:
            continue
        print(
            f"  {key:<18} pool={len(row['universe']):2}  "
            f"rotation={irp['total_return']:+7.2%} (ann {irp['annual_return']:6.2%})  "
            f"510300={bmp['total_return']:+7.2%} (ann {bmp['annual_return']:6.2%})"
        )


def _print_part2(payload: dict[str, Any]) -> None:
    print("\n========== Part 2: 美股 SPDR 行业轮动 同规则对比 ==========")
    print(f"数据: {payload['start']} ~ {payload['end']}")
    sr = payload["sector_rotation_full"]
    spy = payload["benchmark_spy_full"]
    print(f"SPDR轮动: ann={sr['annual_return']:.2%} total={sr['total_return']:.2%} mdd={sr['max_drawdown']:.2%}")
    print(f"SPY:      ann={spy['annual_return']:.2%} total={spy['total_return']:.2%} mdd={spy['max_drawdown']:.2%}")
    print("\n分阶段 total_return | SPDR轮动 vs SPY:")
    for key, row in payload["periods"].items():
        srp = row["sector_rotation"]
        spyp = row["benchmark_spy"]
        if srp["days"] <= 0:
            continue
        print(
            f"  {key:<12} rotation={srp['total_return']:+7.2%} (ann {srp['annual_return']:6.2%})  "
            f"SPY={spyp['total_return']:+7.2%} (ann {spyp['annual_return']:6.2%})"
        )


def _print_cross_market(cn: dict[str, Any], us: dict[str, Any]) -> None:
    print("\n========== 跨市场同规则对照 (2021–2026) ==========")
    cn21 = cn["periods"]["recent_2021_2026"]["industry_rotation"]
    cn510 = cn["periods"]["recent_2021_2026"]["benchmark_510300"]
    us21 = us["periods"]["2021_2026"]["sector_rotation"]
    usspy = us["periods"]["2021_2026"]["benchmark_spy"]
    print(
        f"A股行业轮动  ann={cn21['annual_return']:.2%} mdd={cn21['max_drawdown']:.2%} | "
        f"510300 ann={cn510['annual_return']:.2%}"
    )
    print(
        f"美股SPDR轮动 ann={us21['annual_return']:.2%} mdd={us21['max_drawdown']:.2%} | "
        f"SPY ann={usspy['annual_return']:.2%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-horizon CN industry rotation and US sector rotation comparison.")
    parser.add_argument("--start", default="2017-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--part", choices=("1", "2", "all"), default="all")
    args = parser.parse_args()

    output: dict[str, Any] = {"config": {"start": args.start, "end": args.end}}
    if args.part in {"1", "all"}:
        output["part1_cn_long_horizon"] = run_part1_cn_long_horizon(start=args.start, end=args.end)
        _print_part1(output["part1_cn_long_horizon"])
    if args.part in {"2", "all"}:
        output["part2_us_sector_rotation"] = run_part2_us_comparison(start=args.start, end=args.end)
        _print_part2(output["part2_us_sector_rotation"])
    if args.part == "all" and "part1_cn_long_horizon" in output and "part2_us_sector_rotation" in output:
        _print_cross_market(output["part1_cn_long_horizon"], output["part2_us_sector_rotation"])

    if args.json_output:
        args.json_output.write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
