#!/usr/bin/env python3
"""Phase 2.3: three-track return blend (aggressive ETF + vol25 MA120 + expanded dividend)."""

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
PIPELINE_SRC = ROOT.parent / "CnEquitySnapshotPipelines" / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, SCRIPTS, PIPELINE_SRC, QPK_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_aggressive  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS,
)
from research_cn_dividend_quality_snapshot_proxy_backtest import (  # noqa: E402
    build_market_history_from_downloads,
    build_monthly_factor_panel,
    run_snapshot_proxy_backtest,
)
from research_cn_etf_momentum_stock_combo_proxy_backtest import (  # noqa: E402
    _metrics_from_returns,
    _run_preset_daily_returns,
)
from research_cn_ma120_vol_and_combo_scan import DEFAULT_END, DEFAULT_START, MDD_BUDGET  # noqa: E402
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset,
)
from research_cn_us_long_horizon_comparison import (  # noqa: E402
    CN_UNIVERSE_FULL,
    _download_cn_history,
    _metrics_slice,
    _run_cn_rotation,
    _window_with_warmup,
)

DEFAULT_ETF_WEIGHT = 0.50
DEFAULT_STOCK_WEIGHT = 0.30
DEFAULT_DIVIDEND_WEIGHT = 0.20


def _combine_weighted_returns(
    legs: list[tuple[str, pd.Series, float]],
) -> pd.Series:
    if not legs:
        return pd.Series(dtype=float)
    total_weight = sum(weight for _, _, weight in legs)
    if total_weight <= 0:
        raise ValueError("combined weights must be positive")
    frames = {
        name: series.rename(name)
        for name, series, _weight in legs
    }
    aligned = pd.concat(frames.values(), axis=1, join="inner").sort_index()
    if aligned.empty:
        return pd.Series(dtype=float)
    combo = pd.Series(0.0, index=aligned.index, dtype=float)
    for name, _series, weight in legs:
        combo = combo + (float(weight) / total_weight) * aligned[name].fillna(0.0)
    return combo


def run_tri_track_blend(
    *,
    start: str,
    end: str,
    etf_weight: float = DEFAULT_ETF_WEIGHT,
    stock_weight: float = DEFAULT_STOCK_WEIGHT,
    dividend_weight: float = DEFAULT_DIVIDEND_WEIGHT,
    stock_preset_key: str = CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    dividend_universe_mode: str = "expanded",
    expanded_top_n: int = 40,
    holdings_count: int = 4,
) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    target_vol = float(industry_aggressive.DEFAULT_TARGET_ANNUAL_VOLATILITY)

    industry_history = _download_cn_history(start=download_start, end=end)
    industry_window = _window_with_warmup(industry_history, start, end)
    industry_result = _run_cn_rotation(
        industry_window,
        universe=CN_UNIVERSE_FULL,
        sentiment_mode="off",
        target_annual_volatility=target_vol,
    )
    etf_slice = industry_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]

    stock_preset = STOCK_MOMENTUM_MA120_VOL_TUNING_PRESETS[stock_preset_key]
    stock_history, _, active = _load_universe_bundle(
        stock_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )
    stock_runtime = _materialize_preset(stock_preset, stock_universe=active)
    stock_slice = _run_preset_daily_returns(stock_history, stock_runtime).loc[
        pd.Timestamp(start) : pd.Timestamp(end)
    ]

    dividend_panel, panel_diag = build_monthly_factor_panel(
        start=start,
        end=end,
        universe_mode=dividend_universe_mode,
        expanded_top_n=expanded_top_n,
    )
    dividend_universe = tuple(panel_diag["symbols"])
    dividend_history = build_market_history_from_downloads(
        symbols=dividend_universe,
        start=start,
        end=end,
    )
    dividend_result = run_snapshot_proxy_backtest(
        dividend_panel,
        dividend_history,
        strategy_kwargs={"holdings_count": int(holdings_count)},
    )
    dividend_slice = dividend_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]

    combo_slice = _combine_weighted_returns(
        [
            ("aggressive_etf", etf_slice, etf_weight),
            ("vol25_ma120", stock_slice, stock_weight),
            ("expanded_dividend", dividend_slice, dividend_weight),
        ]
    )

    def _leg_metrics(series: pd.Series) -> dict[str, float | int]:
        return _metrics_from_returns(series)

    return {
        "track": "tri_track_blend",
        "start": start,
        "end": end,
        "mdd_budget": MDD_BUDGET,
        "weights": {
            "aggressive_etf": etf_weight,
            "vol25_ma120": stock_weight,
            "expanded_dividend": dividend_weight,
        },
        "stock_preset": stock_preset_key,
        "dividend_universe_mode": dividend_universe_mode,
        "legs": {
            "aggressive_etf": _leg_metrics(etf_slice),
            "vol25_ma120": _leg_metrics(stock_slice),
            "expanded_dividend": _leg_metrics(dividend_slice),
        },
        "combo": _leg_metrics(combo_slice),
        "periods": {
            "bear_2021_2022": {
                "combo": _metrics_slice(combo_slice, "2021-01-01", "2022-12-31"),
                "aggressive_etf": _metrics_slice(etf_slice, "2021-01-01", "2022-12-31"),
                "vol25_ma120": _metrics_slice(stock_slice, "2021-01-01", "2022-12-31"),
                "expanded_dividend": _metrics_slice(dividend_slice, "2021-01-01", "2022-12-31"),
            },
            "oos_2024_2026": {
                "combo": _metrics_slice(combo_slice, "2024-01-01", end),
                "aggressive_etf": _metrics_slice(etf_slice, "2024-01-01", end),
                "vol25_ma120": _metrics_slice(stock_slice, "2024-01-01", end),
                "expanded_dividend": _metrics_slice(dividend_slice, "2024-01-01", end),
            },
        },
        "within_mdd_budget": float(_leg_metrics(combo_slice)["max_drawdown"]) >= MDD_BUDGET,
        "limitations": [
            "return-level blend (50/30/20) rather than unified multi-asset portfolio simulation",
            f"ETF leg aggressive vol_target={target_vol:.0%}",
            f"stock leg preset={stock_preset_key}",
            f"dividend leg universe_mode={dividend_universe_mode}",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    weights = payload["weights"]
    print("\n=== P2.3 三轨 paper 组合（return blend）===\n")
    print(
        f"权重: aggressive={weights['aggressive_etf']:.0%} | "
        f"vol25={weights['vol25_ma120']:.0%} | "
        f"dividend={weights['expanded_dividend']:.0%}"
    )
    print(f"区间: {payload['start']} ~ {payload['end']}")
    combo = payload["combo"]
    print(
        f"\n组合       ann={combo['annual_return']:6.2%} mdd={combo['max_drawdown']:7.2%} "
        f"total={combo['total_return']:7.2%}"
    )
    for leg_name, leg in payload["legs"].items():
        print(
            f"{leg_name:<18} ann={leg['annual_return']:6.2%} mdd={leg['max_drawdown']:7.2%} "
            f"total={leg['total_return']:7.2%}"
        )
    oos = payload["periods"]["oos_2024_2026"]
    print(
        f"\nOOS 2024+: combo={oos['combo']['total_return']:+7.2%} | "
        f"aggressive={oos['aggressive_etf']['total_return']:+7.2%} | "
        f"vol25={oos['vol25_ma120']['total_return']:+7.2%} | "
        f"dividend={oos['expanded_dividend']['total_return']:+7.2%}"
    )
    flag = "✓" if payload["within_mdd_budget"] else "✗"
    print(f"\nMDD budget {payload['mdd_budget']:.0%}: [{flag}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="MA120 Phase 2.3 tri-track blend proxy.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--etf-weight", type=float, default=DEFAULT_ETF_WEIGHT)
    parser.add_argument("--stock-weight", type=float, default=DEFAULT_STOCK_WEIGHT)
    parser.add_argument("--dividend-weight", type=float, default=DEFAULT_DIVIDEND_WEIGHT)
    parser.add_argument(
        "--stock-preset",
        default=CSI500_MA120_RETURN_OPTIMIZED_PRESET_KEY,
    )
    parser.add_argument("--dividend-universe-mode", default="expanded")
    parser.add_argument("--expanded-top-n", type=int, default=40)
    parser.add_argument("--holdings-count", type=int, default=4)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run_tri_track_blend(
        start=args.start,
        end=args.end,
        etf_weight=args.etf_weight,
        stock_weight=args.stock_weight,
        dividend_weight=args.dividend_weight,
        stock_preset_key=args.stock_preset,
        dividend_universe_mode=args.dividend_universe_mode,
        expanded_top_n=args.expanded_top_n,
        holdings_count=args.holdings_count,
    )
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
