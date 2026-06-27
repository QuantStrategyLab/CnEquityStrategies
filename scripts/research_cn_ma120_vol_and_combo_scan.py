#!/usr/bin/env python3
"""MA120 risk-off vol tuning + ETF/stock weight grid scan (research)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, SCRIPTS, QPK_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.proxy_simulator import compute_backtest_metrics  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS,
)
from research_cn_dual_track_combo_proxy_backtest import _combine_daily_returns  # noqa: E402
from research_cn_etf_momentum_stock_combo_proxy_backtest import (  # noqa: E402
    _metrics_from_returns,
    _run_preset_daily_returns,
)
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset,
)
from research_cn_us_long_horizon_comparison import (  # noqa: E402
    _metrics_slice,
    _run_cn_rotation,
    _window_with_warmup,
    _download_cn_history,
    CN_UNIVERSE_FULL,
)

DEFAULT_START = "2021-01-01"
DEFAULT_END = "2026-06-27"
DEFAULT_ETF_WEIGHTS = (0.0, 0.30, 0.50, 0.70, 1.0)
MDD_BUDGET = -0.35


def _periods(end: str) -> dict[str, tuple[str, str]]:
    return {
        "full": (DEFAULT_START, end),
        "bear_2021_2022": ("2021-01-01", "2022-12-31"),
        "oos_2024_2026": ("2024-01-01", end),
    }


def run_ma120_vol_matrix(*, start: str, end: str) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    base_preset = next(iter(STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.values()))
    stock_history, candidate_universe, active = _load_universe_bundle(
        base_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )
    variants: dict[str, dict[str, Any]] = {}
    for key, preset in STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.items():
        runtime = _materialize_preset(preset, stock_universe=active)
        returns = _run_preset_daily_returns(stock_history, runtime)
        sliced = returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        overall = _metrics_from_returns(sliced)
        periods = {
            period_key: _metrics_slice(sliced, pstart, pend)
            for period_key, (pstart, pend) in _periods(end).items()
        }
        variants[key] = {
            "key": key,
            "label": preset.get("label"),
            "target_annual_volatility": preset.get("target_annual_volatility"),
            "overall": overall,
            "periods": periods,
            "within_mdd_budget": float(overall["max_drawdown"]) >= MDD_BUDGET,
        }
    ranked = sorted(
        variants.values(),
        key=lambda row: (row["overall"]["annual_return"], row["overall"]["max_drawdown"]),
        reverse=True,
    )
    return {
        "track": "ma120_vol_tune",
        "start": start,
        "end": end,
        "mdd_budget": MDD_BUDGET,
        "universe": {
            "candidate_count": len(candidate_universe),
            "active_count": len(active),
        },
        "variants": variants,
        "ranked_by_ann": [row["key"] for row in ranked],
        "best_within_budget": next(
            (row["key"] for row in ranked if row["within_mdd_budget"]),
            None,
        ),
    }


def run_combo_weight_grid(
    *,
    start: str,
    end: str,
    stock_preset_keys: tuple[str, ...],
    etf_weights: tuple[float, ...] = DEFAULT_ETF_WEIGHTS,
    industry_profile: str = "conservative",
) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    industry_history = _download_cn_history(start=download_start, end=end)
    industry_window = _window_with_warmup(industry_history, start, end)
    target_vol = 0.25 if industry_profile == "aggressive" else 0.20
    industry_result = _run_cn_rotation(
        industry_window,
        universe=CN_UNIVERSE_FULL,
        sentiment_mode="off",
        target_annual_volatility=target_vol,
    )
    etf_returns = industry_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]

    base_preset = STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS[stock_preset_keys[0]]
    stock_history, _, active = _load_universe_bundle(
        base_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )

    stock_returns_cache: dict[str, pd.Series] = {}
    grid: list[dict[str, Any]] = []
    for stock_key in stock_preset_keys:
        preset = STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS[stock_key]
        runtime = _materialize_preset(preset, stock_universe=active)
        stock_returns_cache[stock_key] = _run_preset_daily_returns(stock_history, runtime).loc[
            pd.Timestamp(start) : pd.Timestamp(end)
        ]
        for etf_w in etf_weights:
            stock_w = max(0.0, 1.0 - float(etf_w))
            if stock_w <= 0.0:
                combo = etf_returns
            elif etf_w <= 0.0:
                combo = stock_returns_cache[stock_key]
            else:
                combo = _combine_daily_returns(
                    etf_returns,
                    stock_returns_cache[stock_key],
                    industry_weight=etf_w,
                    dividend_weight=stock_w,
                )
            overall = _metrics_from_returns(combo)
            grid.append(
                {
                    "stock_preset": stock_key,
                    "etf_weight": etf_w,
                    "stock_weight": stock_w,
                    "industry_profile": industry_profile,
                    "overall": overall,
                    "oos_2024_2026": _metrics_slice(combo, "2024-01-01", end),
                    "bear_2021_2022": _metrics_slice(combo, "2021-01-01", "2022-12-31"),
                    "within_mdd_budget": float(overall["max_drawdown"]) >= MDD_BUDGET,
                }
            )

    within_budget = [row for row in grid if row["within_mdd_budget"]]
    best_ann = max(within_budget, key=lambda row: row["overall"]["annual_return"]) if within_budget else None
    best_sharpe = (
        max(
            within_budget,
            key=lambda row: row["overall"].get("sharpe_ratio", float("-inf")),
        )
        if within_budget
        else None
    )
    return {
        "track": "etf_stock_weight_grid",
        "start": start,
        "end": end,
        "mdd_budget": MDD_BUDGET,
        "industry_profile": industry_profile,
        "stock_preset_keys": list(stock_preset_keys),
        "etf_weights_scanned": list(etf_weights),
        "grid": grid,
        "best_within_budget_by_ann": best_ann,
        "best_within_budget_by_sharpe": best_sharpe,
    }


def _print_ma120_report(payload: dict[str, Any]) -> None:
    print("\n=== MA120 risk-off vol 调参（2021–2026）===\n")
    print(f"MDD budget: {payload['mdd_budget']:.0%}")
    for key in payload["ranked_by_ann"]:
        row = payload["variants"][key]
        overall = row["overall"]
        flag = "✓" if row["within_mdd_budget"] else "✗"
        print(
            f"  [{flag}] {key:<45} vol={row['target_annual_volatility']:.0%} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print(f"\nBest within budget: {payload['best_within_budget']}")


def _print_grid_report(payload: dict[str, Any]) -> None:
    print("\n=== ETF + MA120 个股 权重网格 ===\n")
    rows = sorted(
        [row for row in payload["grid"] if row["within_mdd_budget"]],
        key=lambda row: row["overall"]["annual_return"],
        reverse=True,
    )
    for row in rows[:12]:
        overall = row["overall"]
        print(
            f"  etf={row['etf_weight']:.0%} stock={row['stock_weight']:.0%} "
            f"preset={row['stock_preset'][-20:]:<20} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"oos={row['oos_2024_2026']['total_return']:+7.2%}"
        )
    best = payload.get("best_within_budget_by_ann")
    if best:
        o = best["overall"]
        print(
            f"\nBest (ann, MDD≤35%): etf={best['etf_weight']:.0%} stock={best['stock_weight']:.0%} "
            f"preset={best['stock_preset']} ann={o['annual_return']:.2%} mdd={o['max_drawdown']:.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="MA120 vol tune + ETF/stock weight grid.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--mode",
        choices=("all", "ma120_vol", "weight_grid"),
        default="all",
    )
    parser.add_argument(
        "--industry-profile",
        choices=("conservative", "aggressive"),
        default="conservative",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    stock_keys = tuple(STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS.keys())
    payload: dict[str, Any] = {"start": args.start, "end": args.end}
    if args.mode in {"all", "ma120_vol"}:
        payload["ma120_vol_matrix"] = run_ma120_vol_matrix(start=args.start, end=args.end)
        _print_ma120_report(payload["ma120_vol_matrix"])
    if args.mode in {"all", "weight_grid"}:
        payload["weight_grid"] = run_combo_weight_grid(
            start=args.start,
            end=args.end,
            stock_preset_keys=stock_keys,
            industry_profile=args.industry_profile,
        )
        _print_grid_report(payload["weight_grid"])
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
