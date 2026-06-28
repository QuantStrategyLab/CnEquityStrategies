#!/usr/bin/env python3
"""Unified dual-track combo backtest — aggressive ETF leg + CSI500 stock leg.

Shares a single ProxyBacktest calendar and combines weights at rebalance time
(rather than blending return curves post-hoc).

Usage:
    python scripts/research_cn_combo_unified_simulator.py
    python scripts/research_cn_combo_unified_simulator.py \\
        --etf-weight 0.5 --stock-weight 0.5 \\
        --json-output docs/research/cn_combo_unified_20260628.json
    python scripts/research_cn_combo_unified_simulator.py \\
        --etf-weights "0,0.3,0.5,0.7,1.0"  # sweep mode
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for candidate in (SRC, SCRIPTS):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.strategies.combo_wrapper import build_combo_target_weights
from research_cn_industry_etf_rotation_validation import _download_market_history  # noqa: E402
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset as _materialize_stock_preset,
)
from research_cn_momentum_stock_rotation_proxy import resolve_momentum_stock_universe  # noqa: E402

DEFAULT_START = "2021-01-01"
DEFAULT_END = "2026-06-27"

# ETF-aggressive defaults (vol25%, full pool, monthly, no risk-off)
ETF_PRESET_KWARGS: dict[str, Any] = {
    "target_annual_volatility": 0.25,
    "top_n": 5,
    "sentiment_mode": "off",
    "enable_benchmark_risk_off": False,
    "universe_symbols": ("512760", "512170", "515030", "512800", "512690", "159928", "159915", "159995", "159994"),
    "min_history_days": 25,
    "trend_window_days": 20,
    "momentum_window_days": 20,
    "benchmark_trend_window_days": 20,
    "volatility_window_days": 20,
}

# Stock momentum presets (vol25 MA120 risk-off)
STOCK_MOMENTUM_PRESET_KEY = "momentum_csi500_top5_vol25_ma120_riskoff"
STOCK_PRESET_OVERRIDES: dict[str, Any] = {
    "target_annual_volatility": 0.25,
    "top_n": 5,
    "enable_benchmark_risk_off": True,
    "benchmark_symbol": "510300",
    "defensive_symbols": ("510300",),
    "benchmark_trend_window_days": 120,
    "sentiment_mode": "off",
}


def _run_combo_backtest(
    etf_history: pd.DataFrame,
    stock_history: pd.DataFrame,
    stock_universe: tuple[str, ...],
    *,
    etf_weight: float = 0.30,
    stock_weight: float = 0.70,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
) -> dict[str, Any]:
    stock_preset = _build_stock_materialized(stock_history, stock_universe)
    etf_config = dict(ETF_PRESET_KWARGS)

    def combo_signal_fn(market_history: Any, current_holdings: Any = None) -> tuple[dict[str, float], dict[str, object]]:
        weights, metadata = build_combo_target_weights(
            market_history,
            current_holdings=current_holdings,
            etf_config=etf_config,
            stock_config=stock_preset,
            etf_weight=etf_weight,
            stock_weight=stock_weight,
        )
        return weights, metadata

    for _key in ("universe_symbols", "pit_index_code", "rebalance_frequency", "min_history_days",
                 "profile_variant", "label", "liquid_top_n", "universe_mode",
                 "execution_cash_reserve_ratio"):
        stock_preset.pop(_key, None)
    full_market_history = pd.concat([etf_history, stock_history], ignore_index=True)
    full_market_history = full_market_history.drop_duplicates(subset=["date", "symbol"]).sort_values(
        ["date", "symbol"]
    ).reset_index(drop=True)

    from cn_equity_strategies.backtest.proxy_simulator import run_proxy_backtest, ProxyBacktestConfig

    # Filter market history to the requested date range
    full_market_history = full_market_history.loc[
        (full_market_history["date"] >= pd.Timestamp(start))
        & (full_market_history["date"] <= pd.Timestamp(end))
    ].reset_index(drop=True)

    config = ProxyBacktestConfig(
        initial_cash=1_000_000.0,
        commission_rate=0.0003,
        min_history_days=20,
        cash_reserve_ratio=0.02,
        lot_size=100,
    )
    all_symbols = tuple(dict.fromkeys([*full_market_history["symbol"].unique()]))
    result = run_proxy_backtest(
        market_history=full_market_history,
        strategy_signal_fn=combo_signal_fn,
        config=config,
        universe_symbols=all_symbols,
        strategy_kwargs={},
    )
    metrics = _compute_period_metrics(result.daily_returns)
    return {
        "config": {
            "etf_weight": etf_weight,
            "stock_weight": stock_weight,
            "etf_preset": ETF_PRESET_KWARGS,
            "stock_preset_key": STOCK_MOMENTUM_PRESET_KEY,
        },
        "overall": metrics["full"],
        "period_metrics": metrics,
        "equity_curve": {str(k): v for k, v in result.equity_curve.items()} if result.equity_curve is not None else {},
    }


def _build_stock_materialized(
    stock_history: pd.DataFrame,
    stock_universe: tuple[str, ...],
) -> dict[str, Any]:
    from cn_equity_strategies.strategies.industry_etf_rotation_presets import (
        STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS,
    )
    preset = deepcopy(STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.get(STOCK_MOMENTUM_PRESET_KEY, {}))
    preset.update(STOCK_PRESET_OVERRIDES)
    runtime = _materialize_stock_preset(preset, stock_universe=stock_universe)
    return runtime


def _compute_period_metrics(
    daily_returns: pd.Series | list[float] | tuple[float, ...] | None,
) -> dict[str, dict[str, float]]:
    from cn_equity_strategies.backtest.proxy_simulator import compute_backtest_metrics
    if daily_returns is None:
        return {"full": {"days": 0, "total_return": 0.0, "annual_return": 0.0, "max_drawdown": 0.0}}
    series = pd.Series(daily_returns) if not isinstance(daily_returns, pd.Series) else daily_returns
    return {"full": compute_backtest_metrics(series)}


def run_combo(
    *,
    etf_weight: float = 0.30,
    stock_weight: float = 0.70,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    max_symbols: int | None = None,
) -> dict[str, Any]:

    etf_download_start = (pd.Timestamp(start) - pd.Timedelta(days=800)).date().isoformat()
    etf_history = _download_market_history(start=etf_download_start, end=end)
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=800)).date().isoformat()
    stock_history, candidate_universe, active = _load_universe_bundle(
        {"universe_mode": "csi500"},
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=max_symbols,
    )
    return _run_combo_backtest(
        etf_history,
        stock_history,
        active,
        etf_weight=etf_weight,
        stock_weight=stock_weight,
        start=start,
        end=end,
    )


def run_combo_sweep(
    *,
    etf_weights: list[float],
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    max_symbols: int | None = None,
) -> list[dict[str, Any]]:
    etf_download_start = (pd.Timestamp(start) - pd.Timedelta(days=800)).date().isoformat()
    etf_history = _download_market_history(start=etf_download_start, end=end)
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=800)).date().isoformat()
    stock_history, candidate_universe, active = _load_universe_bundle(
        {"universe_mode": "csi500"},
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=max_symbols,
    )
    results: list[dict[str, Any]] = []
    for ew in etf_weights:
        sw = round(1.0 - ew, 4)
        if sw < 0:
            continue
        result = _run_combo_backtest(
            etf_history,
            stock_history,
            active,
            etf_weight=ew,
            stock_weight=sw,
            start=start,
            end=end,
        )
        results.append(result)
    results.sort(key=lambda r: r["overall"].get("sharpe_ratio", 0), reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified dual-track combo backtest.")
    parser.add_argument("--etf-weight", type=float, default=0.30)
    parser.add_argument("--stock-weight", type=float, default=0.70)
    parser.add_argument(
        "--etf-weights",
        type=str,
        default=None,
        help="Comma-separated ETF weights for sweep mode (e.g. '0,0.3,0.5,0.7,1.0')",
    )
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--max-symbols", type=int, default=100, help="Limit CSI500 stock downloads for speed")
    args = parser.parse_args()

    if args.etf_weights:
        weights = [float(w.strip()) for w in args.etf_weights.split(",") if w.strip()]
        print(f"Sweeping ETF weights: {weights}")
        results = run_combo_sweep(etf_weights=weights, start=args.start, end=args.end, max_symbols=args.max_symbols)
        print(f"\n{'etf_weight':>12s} {'stock_weight':>13s} {'ann_ret':>8s} {'mdd':>8s} {'sharpe':>8s}")
        for r in results:
            o = r["overall"]
            ew = r["config"]["etf_weight"]
            sw = r["config"]["stock_weight"]
            print(f"{ew:>12.0%} {sw:>13.0%} {o.get('annual_return', 0):>8.2%} {o.get('max_drawdown', 0):>8.2%} {o.get('sharpe_ratio', 0):>8.2f}")
    else:
        print(f"Combo: {args.etf_weight:.0%} ETF + {args.stock_weight:.0%} stock")
        result = run_combo(
            etf_weight=args.etf_weight,
            stock_weight=args.stock_weight,
            start=args.start,
            end=args.end,
            max_symbols=args.max_symbols,
        )
        o = result["overall"]
        print(f"  Annual return: {o.get('annual_return', 0):.2%}")
        print(f"  Max drawdown:  {o.get('max_drawdown', 0):.2%}")
        print(f"  Sharpe:        {o.get('sharpe_ratio', 0):.2f}")
        print(f"  Total return:  {o.get('total_return', 0):.2%}")

    if args.json_output:
        payload = {"start": args.start, "end": args.end}
        if args.etf_weights:
            payload["combo_grid"] = results
        else:
            payload["combo"] = result
        args.json_output.write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nSaved to {args.json_output}")


if __name__ == "__main__":
    main()
