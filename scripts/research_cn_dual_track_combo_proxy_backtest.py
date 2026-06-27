#!/usr/bin/env python3
"""Dual-track combo proxy: industry rotation + dividend quality snapshot."""

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

from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    compute_backtest_metrics,
    run_proxy_backtest,
)

from research_cn_dividend_quality_snapshot_proxy_backtest import (  # noqa: E402
    SAFE_HAVEN,
    build_market_history_from_downloads,
    build_monthly_factor_panel,
    run_snapshot_proxy_backtest,
)
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_aggressive_rotation  # noqa: E402
from research_cn_us_long_horizon_comparison import (  # noqa: E402
    CN_BENCHMARK,
    CN_UNIVERSE_FULL,
    _download_cn_history,
    _metrics_slice,
    _run_cn_rotation,
    _window_with_warmup,
)

DEFAULT_INDUSTRY_WEIGHT = 0.70
DEFAULT_DIVIDEND_WEIGHT = 0.30


def _combine_daily_returns(
    industry_returns: pd.Series,
    dividend_returns: pd.Series,
    *,
    industry_weight: float,
    dividend_weight: float,
) -> pd.Series:
    aligned = pd.concat(
        [industry_returns.rename("industry"), dividend_returns.rename("dividend")],
        axis=1,
        join="inner",
    ).sort_index()
    if aligned.empty:
        return pd.Series(dtype=float)
    total_weight = float(industry_weight) + float(dividend_weight)
    if total_weight <= 0:
        raise ValueError("combined weights must be positive")
    industry_share = float(industry_weight) / total_weight
    dividend_share = float(dividend_weight) / total_weight
    return industry_share * aligned["industry"].fillna(0.0) + dividend_share * aligned["dividend"].fillna(0.0)


def _metrics_from_returns(daily_returns: pd.Series) -> dict[str, float | int]:
    return compute_backtest_metrics(daily_returns.dropna())


def run_dual_track_combo(
    *,
    start: str,
    end: str,
    industry_weight: float = DEFAULT_INDUSTRY_WEIGHT,
    dividend_weight: float = DEFAULT_DIVIDEND_WEIGHT,
    holdings_count: int = 4,
    industry_profile: str = "conservative",
    dividend_universe_mode: str = "staging",
    expanded_top_n: int = 40,
    refresh_sector_map: bool = False,
) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    industry_history = _download_cn_history(start=download_start, end=end)
    industry_window = _window_with_warmup(industry_history, start, end)
    target_vol = (
        float(industry_aggressive_rotation.DEFAULT_TARGET_ANNUAL_VOLATILITY)
        if industry_profile == "aggressive"
        else 0.20
    )
    industry_result = _run_cn_rotation(
        industry_window,
        universe=CN_UNIVERSE_FULL,
        sentiment_mode="off",
        target_annual_volatility=target_vol,
    )
    industry_bench = run_proxy_backtest(
        industry_window,
        lambda _h, **_k: ({CN_BENCHMARK: 1.0}, {}),
        config=ProxyBacktestConfig(min_history_days=220),
        universe_symbols=(CN_BENCHMARK,),
    )

    dividend_panel, panel_diag = build_monthly_factor_panel(
        start=start,
        end=end,
        universe_mode=dividend_universe_mode,
        expanded_top_n=expanded_top_n,
        refresh_sector_map=refresh_sector_map,
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
    dividend_bench = run_proxy_backtest(
        dividend_history,
        lambda _h, **_k: ({SAFE_HAVEN: 1.0}, {}),
        config=ProxyBacktestConfig(min_history_days=252),
        universe_symbols=(SAFE_HAVEN,),
    )

    industry_slice = industry_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    dividend_slice = dividend_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    combo_slice = _combine_daily_returns(
        industry_slice,
        dividend_slice,
        industry_weight=industry_weight,
        dividend_weight=dividend_weight,
    )

    periods = {
        "full": (start, end),
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_2026": ("2023-01-01", end),
    }

    def _period_bundle(series: pd.Series) -> dict[str, dict[str, float | int]]:
        return {
            key: _metrics_slice(series, pstart, pend)
            for key, (pstart, pend) in periods.items()
        }

    return {
        "start": start,
        "end": end,
        "weights": {
            "industry_rotation": industry_weight,
            "dividend_quality": dividend_weight,
        },
        "industry_profile": industry_profile,
        "industry_vol_target": target_vol,
        "industry_universe": list(CN_UNIVERSE_FULL),
        "dividend_universe": list(dividend_universe),
        "dividend_universe_mode": dividend_universe_mode,
        "dividend_panel_diagnostics": panel_diag,
        "full_sample": {
            "combo": _metrics_from_returns(combo_slice),
            "industry_rotation": _metrics_from_returns(industry_slice),
            "dividend_quality": _metrics_from_returns(dividend_slice),
            "510300_from_industry_data": _metrics_from_returns(
                industry_bench.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
            ),
            "510300_from_dividend_data": _metrics_from_returns(
                dividend_bench.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
            ),
        },
        "periods": {
            key: {
                "combo": _metrics_slice(combo_slice, pstart, pend),
                "industry_rotation": _metrics_slice(industry_slice, pstart, pend),
                "dividend_quality": _metrics_slice(dividend_slice, pstart, pend),
            }
            for key, (pstart, pend) in periods.items()
        },
        "limitations": [
            "return-level blend (70/30) rather than unified multi-asset portfolio simulation",
            f"industry leg profile={industry_profile} vol_target={target_vol:.0%}",
            f"dividend leg uses universe_mode={dividend_universe_mode}",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    weights = payload["weights"]
    print("\n========== 双轨组合 proxy（行业 + 红利 quality）==========")
    print(
        f"权重: industry={weights['industry_rotation']:.0%} | "
        f"dividend={weights['dividend_quality']:.0%} | "
        f"industry_profile={payload.get('industry_profile', 'conservative')}"
    )
    print(f"区间: {payload['start']} ~ {payload['end']}")
    full = payload["full_sample"]
    combo = full["combo"]
    industry = full["industry_rotation"]
    dividend = full["dividend_quality"]
    bench = full["510300_from_industry_data"]
    print(
        f"组合       ann={combo['annual_return']:6.2%} total={combo['total_return']:7.2%} "
        f"mdd={combo['max_drawdown']:7.2%}"
    )
    print(
        f"行业轮动   ann={industry['annual_return']:6.2%} total={industry['total_return']:7.2%} "
        f"mdd={industry['max_drawdown']:7.2%}"
    )
    print(
        f"红利quality ann={dividend['annual_return']:6.2%} total={dividend['total_return']:7.2%} "
        f"mdd={dividend['max_drawdown']:7.2%}"
    )
    print(
        f"510300     ann={bench['annual_return']:6.2%} total={bench['total_return']:7.2%} "
        f"mdd={bench['max_drawdown']:7.2%}"
    )
    print("\n分阶段 total_return:")
    for key, row in payload["periods"].items():
        if row["combo"]["days"] <= 0:
            continue
        print(
            f"  {key:<10} combo={row['combo']['total_return']:+7.2%} "
            f"(ann {row['combo']['annual_return']:6.2%}) | "
            f"industry={row['industry_rotation']['total_return']:+7.2%} | "
            f"dividend={row['dividend_quality']['total_return']:+7.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Dual-track combo proxy backtest.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--industry-weight", type=float, default=DEFAULT_INDUSTRY_WEIGHT)
    parser.add_argument("--dividend-weight", type=float, default=DEFAULT_DIVIDEND_WEIGHT)
    parser.add_argument("--holdings-count", type=int, default=4)
    parser.add_argument(
        "--industry-profile",
        choices=("conservative", "aggressive"),
        default="conservative",
        help="conservative=vol20%% production preset; aggressive=vol25%% research profile",
    )
    parser.add_argument(
        "--dividend-universe-mode",
        choices=("staging", "expanded", "custom"),
        default="staging",
    )
    parser.add_argument("--expanded-top-n", type=int, default=40)
    parser.add_argument("--refresh-sector-map", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run_dual_track_combo(
        start=args.start,
        end=args.end,
        industry_weight=args.industry_weight,
        dividend_weight=args.dividend_weight,
        holdings_count=args.holdings_count,
        industry_profile=args.industry_profile,
        dividend_universe_mode=args.dividend_universe_mode,
        expanded_top_n=args.expanded_top_n,
        refresh_sector_map=args.refresh_sector_map,
    )
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
