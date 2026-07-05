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
    SnapshotProxyBacktestConfig,
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
COMBO_WEIGHT_GRID = (0.60, 0.70, 0.80, 0.85, 0.90, 0.95)
COMBO_MDD_BUDGET = -0.20
COMBO_PROMOTION_MDD_GAP = 0.01


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


def _scan_combo_weight_grid(
    industry_returns: pd.Series,
    dividend_returns: pd.Series,
    industry_metrics: dict[str, float | int],
    *,
    industry_recent_total_return: float,
    weight_grid: tuple[float, ...] = COMBO_WEIGHT_GRID,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for industry_weight in weight_grid:
        dividend_weight = 1.0 - float(industry_weight)
        if dividend_weight <= 0.0:
            continue
        combo_returns = _combine_daily_returns(
            industry_returns,
            dividend_returns,
            industry_weight=industry_weight,
            dividend_weight=dividend_weight,
        )
        overall = _metrics_from_returns(combo_returns)
        period_2023_2026 = _metrics_slice(combo_returns, "2023-01-01", str(combo_returns.index.max().date()))
        rows.append(
            {
                "industry_weight": float(industry_weight),
                "dividend_weight": float(dividend_weight),
                "overall": overall,
                "within_mdd_budget": float(overall["max_drawdown"]) >= COMBO_MDD_BUDGET,
                "beats_industry_full_return": float(overall["annual_return"]) >= float(industry_metrics["annual_return"]),
                "beats_industry_recent_return": float(period_2023_2026["total_return"]) >= float(industry_recent_total_return),
                "mdd_vs_industry": float(overall["max_drawdown"]) - float(industry_metrics["max_drawdown"]),
                "periods": {
                    "2021_2022": _metrics_slice(combo_returns, "2021-01-01", "2022-12-31"),
                    "2023_2026": period_2023_2026,
                },
            }
        )
    rows.sort(
        key=lambda row: (
            row["beats_industry_recent_return"],
            row["beats_industry_full_return"],
            row["within_mdd_budget"],
            row["overall"]["annual_return"],
        ),
        reverse=True,
    )
    return rows


def _select_combo_weight(
    weight_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not weight_rows:
        return None
    promotable = [
        row
        for row in weight_rows
        if row["within_mdd_budget"]
        and row["beats_industry_recent_return"]
        and row["beats_industry_full_return"]
        and row["mdd_vs_industry"] >= -COMBO_PROMOTION_MDD_GAP
    ]
    if promotable:
        return max(promotable, key=lambda row: row["overall"]["annual_return"])
    return max(weight_rows, key=lambda row: row["overall"]["annual_return"])


def _month_end_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    normalized = pd.Series(index).dt.normalize()
    grouped = normalized.groupby([normalized.dt.year, normalized.dt.month]).max()
    return [pd.Timestamp(value) for value in grouped.sort_index()]


def _lookback_return(series: pd.Series, end: pd.Timestamp, lookback_days: int) -> float:
    window = series.loc[:end].dropna().tail(int(lookback_days))
    if len(window) < 2:
        return 0.0
    equity = (1.0 + window).cumprod()
    return float(equity.iloc[-1] - 1.0)


def _regime_allocation_weights(
    *,
    as_of: pd.Timestamp,
    industry_returns: pd.Series,
    dividend_returns: pd.Series,
    benchmark_returns: pd.Series,
    base_industry_weight: float,
    base_dividend_weight: float,
) -> tuple[float, float, dict[str, float | str]]:
    industry_63 = _lookback_return(industry_returns, as_of, 63)
    industry_126 = _lookback_return(industry_returns, as_of, 126)
    dividend_63 = _lookback_return(dividend_returns, as_of, 63)
    benchmark_126 = _lookback_return(benchmark_returns, as_of, 126)

    regime_score = 0.45 * industry_126 + 0.35 * benchmark_126 + 0.20 * (industry_63 - dividend_63)
    if regime_score >= 0.12:
        weights = (0.85, 0.15)
        regime = "risk_on"
    elif regime_score >= 0.04:
        weights = (0.80, 0.20)
        regime = "strong"
    elif regime_score >= -0.02:
        weights = (0.75, 0.25)
        regime = "neutral"
    elif regime_score >= -0.08:
        weights = (0.70, 0.30)
        regime = "weak"
    else:
        weights = (0.60, 0.40)
        regime = "stress"

    # Blend the regime suggestion with the base allocation so the allocator
    # stays close to the current live-comfortable shape.
    industry_weight = 0.5 * float(base_industry_weight) + 0.5 * weights[0]
    dividend_weight = 0.5 * float(base_dividend_weight) + 0.5 * weights[1]
    total = industry_weight + dividend_weight
    return industry_weight / total, dividend_weight / total, {
        "regime": regime,
        "regime_score": regime_score,
        "industry_63d": industry_63,
        "industry_126d": industry_126,
        "dividend_63d": dividend_63,
        "benchmark_126d": benchmark_126,
    }


def _build_regime_combo_series(
    industry_returns: pd.Series,
    dividend_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    base_industry_weight: float,
    base_dividend_weight: float,
) -> tuple[pd.Series, list[dict[str, object]]]:
    aligned = pd.concat(
        [
            industry_returns.rename("industry"),
            dividend_returns.rename("dividend"),
            benchmark_returns.rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).sort_index()
    if aligned.empty:
        return pd.Series(dtype=float), []

    rebalance_dates = _month_end_rebalance_dates(aligned.index)
    effective_weights: dict[pd.Timestamp, tuple[float, float, dict[str, float | str]]] = {}
    trace: list[dict[str, object]] = []

    for rebalance_date in rebalance_dates:
        if rebalance_date not in aligned.index:
            continue
        industry_weight, dividend_weight, meta = _regime_allocation_weights(
            as_of=rebalance_date,
            industry_returns=aligned["industry"],
            dividend_returns=aligned["dividend"],
            benchmark_returns=aligned["benchmark"],
            base_industry_weight=base_industry_weight,
            base_dividend_weight=base_dividend_weight,
        )
        pos = aligned.index.get_loc(rebalance_date)
        if isinstance(pos, slice):  # pragma: no cover - defensive
            pos = pos.stop - 1
        if pos + 1 < len(aligned.index):
            effective_date = aligned.index[pos + 1]
            effective_weights[effective_date] = (industry_weight, dividend_weight, meta)
            trace.append(
                {
                    "rebalance_date": str(rebalance_date.date()),
                    "effective_date": str(effective_date.date()),
                    "industry_weight": industry_weight,
                    "dividend_weight": dividend_weight,
                    **meta,
                }
            )

    current_weights = (float(base_industry_weight), float(base_dividend_weight))
    combo_values: list[float] = []
    for current_date, row in aligned.iterrows():
        if current_date in effective_weights:
            current_weights = (effective_weights[current_date][0], effective_weights[current_date][1])
        combo_values.append(current_weights[0] * float(row["industry"]) + current_weights[1] * float(row["dividend"]))

    return pd.Series(combo_values, index=aligned.index, dtype=float), trace


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
    allocation_mode: str = "static",
    weight_policy: str = "fixed",
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
        config=ProxyBacktestConfig(min_history_days=60),
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
        config=SnapshotProxyBacktestConfig(min_history_days=60),
        strategy_kwargs={"holdings_count": int(holdings_count)},
    )
    dividend_bench = run_proxy_backtest(
        dividend_history,
        lambda _h, **_k: ({SAFE_HAVEN: 1.0}, {}),
        config=ProxyBacktestConfig(min_history_days=60),
        universe_symbols=(SAFE_HAVEN,),
    )

    industry_slice = industry_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    dividend_slice = dividend_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    industry_metrics = _metrics_from_returns(industry_slice)
    industry_recent_total_return = _metrics_slice(industry_slice, "2023-01-01", end)["total_return"]
    combo_weight_scan = _scan_combo_weight_grid(
        industry_slice,
        dividend_slice,
        industry_metrics,
        industry_recent_total_return=industry_recent_total_return,
    )
    selected_combo = _select_combo_weight(combo_weight_scan) if weight_policy == "scan" else None
    selected_industry_weight = (
        float(selected_combo["industry_weight"]) if selected_combo else float(industry_weight)
    )
    selected_dividend_weight = (
        float(selected_combo["dividend_weight"]) if selected_combo else float(dividend_weight)
    )
    combo_static_slice = _combine_daily_returns(
        industry_slice,
        dividend_slice,
        industry_weight=selected_industry_weight,
        dividend_weight=selected_dividend_weight,
    )
    regime_slice, regime_trace = _build_regime_combo_series(
        industry_slice,
        dividend_slice,
        industry_bench.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)],
        base_industry_weight=selected_industry_weight,
        base_dividend_weight=selected_dividend_weight,
    )
    primary_combo_slice = regime_slice if allocation_mode == "regime" else combo_static_slice

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
            "industry_rotation": selected_industry_weight,
            "dividend_quality": selected_dividend_weight,
            "weight_policy": weight_policy,
        },
        "base_weights": {
            "industry_rotation": industry_weight,
            "dividend_quality": dividend_weight,
        },
        "industry_profile": industry_profile,
        "industry_vol_target": target_vol,
        "industry_universe": list(CN_UNIVERSE_FULL),
        "dividend_universe": list(dividend_universe),
        "dividend_universe_mode": dividend_universe_mode,
        "dividend_panel_diagnostics": panel_diag,
        "combo_weight_scan": combo_weight_scan,
        "combo_weight_selection": selected_combo,
        "full_sample": {
            "combo": _metrics_from_returns(primary_combo_slice),
            "combo_static": _metrics_from_returns(combo_static_slice),
            "combo_regime": _metrics_from_returns(regime_slice),
            "industry_rotation": industry_metrics,
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
                "combo": _metrics_slice(primary_combo_slice, pstart, pend),
                "combo_static": _metrics_slice(combo_static_slice, pstart, pend),
                "combo_regime": _metrics_slice(regime_slice, pstart, pend),
                "industry_rotation": _metrics_slice(industry_slice, pstart, pend),
                "dividend_quality": _metrics_slice(dividend_slice, pstart, pend),
            }
            for key, (pstart, pend) in periods.items()
        },
        "allocation_mode": allocation_mode,
        "primary_combo_mode": "regime" if allocation_mode == "regime" else "static",
        "allocation_trace": regime_trace,
        "limitations": [
            "return-level blend rather than unified multi-asset portfolio simulation",
            f"industry leg profile={industry_profile} vol_target={target_vol:.0%}",
            f"dividend leg uses universe_mode={dividend_universe_mode}",
            "combo live promotion requires beating industry baseline on recent and full-sample return, plus MDD parity",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    weights = payload["weights"]
    base_weights = payload.get("base_weights", weights)
    print("\n========== 双轨组合 proxy（行业 + 红利 quality）==========")
    print(
        f"权重: industry={weights['industry_rotation']:.0%} | "
        f"dividend={weights['dividend_quality']:.0%} | "
        f"policy={weights.get('weight_policy', 'fixed')} | "
        f"industry_profile={payload.get('industry_profile', 'conservative')} | "
        f"allocation_mode={payload.get('primary_combo_mode', 'static')}"
    )
    if base_weights != weights:
        print(
            f"基准权重: industry={base_weights['industry_rotation']:.0%} | "
            f"dividend={base_weights['dividend_quality']:.0%}"
        )
    print(f"区间: {payload['start']} ~ {payload['end']}")
    full = payload["full_sample"]
    combo = full["combo"]
    regime_combo = full.get("combo_regime")
    static_combo = full.get("combo_static")
    industry = full["industry_rotation"]
    dividend = full["dividend_quality"]
    bench = full["510300_from_industry_data"]
    print(
        f"组合       ann={combo['annual_return']:6.2%} total={combo['total_return']:7.2%} "
        f"mdd={combo['max_drawdown']:7.2%}"
    )
    selection = payload.get("combo_weight_selection")
    if selection:
        print(
            f"入选权重   industry={selection['industry_weight']:.0%} | "
            f"dividend={selection['dividend_weight']:.0%} | "
            f"promotable={'yes' if selection['within_mdd_budget'] and selection['beats_industry_recent_return'] and selection['beats_industry_full_return'] else 'no'}"
        )
    if static_combo and payload.get("primary_combo_mode") == "regime":
        print(
            f"静态对照   ann={static_combo['annual_return']:6.2%} total={static_combo['total_return']:7.2%} "
            f"mdd={static_combo['max_drawdown']:7.2%}"
        )
    if regime_combo:
        print(
            f"动态组合   ann={regime_combo['annual_return']:6.2%} total={regime_combo['total_return']:7.2%} "
            f"mdd={regime_combo['max_drawdown']:7.2%}"
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
    parser.add_argument("--allocation-mode", choices=("static", "regime"), default="static")
    parser.add_argument("--weight-policy", choices=("fixed", "scan"), default="fixed")
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
        allocation_mode=args.allocation_mode,
        weight_policy=args.weight_policy,
    )
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
