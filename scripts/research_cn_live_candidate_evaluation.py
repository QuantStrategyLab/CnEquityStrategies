#!/usr/bin/env python3
"""Evaluate runtime-enabled A-share + snapshot strategies for live candidacy."""

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
from cn_equity_strategies.catalog import (  # noqa: E402
    CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_PROFILE,
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
    get_runtime_enabled_profiles,
    get_strategy_metadata,
)
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_aggressive  # noqa: E402
from research_cn_dividend_quality_snapshot_proxy_backtest import (  # noqa: E402
    SAFE_HAVEN,
    build_market_history_from_downloads,
    build_monthly_factor_panel,
    run_snapshot_proxy_backtest,
)
from research_cn_dual_track_combo_proxy_backtest import (  # noqa: E402
    _combine_daily_returns,
    run_dual_track_combo,
)
from research_cn_us_long_horizon_comparison import (  # noqa: E402
    CN_BENCHMARK,
    CN_UNIVERSE_FULL,
    _download_cn_history,
    _metrics_slice,
    _run_cn_rotation,
    _window_with_warmup,
)

DEFAULT_START = "2021-01-01"
DEFAULT_END = "2026-06-27"
MDD_BUDGETS = (-0.30, -0.35)


def _etf_leg_metrics(
    *,
    start: str,
    end: str,
    profile: str,
) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    history = _download_cn_history(start=download_start, end=end)
    window = _window_with_warmup(history, start, end)
    target_vol = (
        float(industry_aggressive.DEFAULT_TARGET_ANNUAL_VOLATILITY)
        if profile == CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE
        else 0.20
    )
    result = _run_cn_rotation(
        window,
        universe=CN_UNIVERSE_FULL,
        sentiment_mode="off",
        target_annual_volatility=target_vol,
    )
    returns = result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    overall = compute_backtest_metrics(returns.dropna())
    return {
        "profile": profile,
        "vol_target": target_vol,
        "overall": overall,
        "periods": {
            "bear_2021_2022": _metrics_slice(returns, "2021-01-01", "2022-12-31"),
            "oos_2024_2026": _metrics_slice(returns, "2024-01-01", end),
        },
    }


def _dividend_leg_metrics(
    *,
    start: str,
    end: str,
    universe_mode: str,
    expanded_top_n: int = 40,
) -> dict[str, Any]:
    panel, panel_diag = build_monthly_factor_panel(
        start=start,
        end=end,
        universe_mode=universe_mode,
        expanded_top_n=expanded_top_n,
        refresh_sector_map=False,
    )
    universe = tuple(panel_diag["symbols"])
    history = build_market_history_from_downloads(symbols=universe, start=start, end=end)
    result = run_snapshot_proxy_backtest(panel, history, strategy_kwargs={"holdings_count": 4})
    returns = result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    overall = compute_backtest_metrics(returns.dropna())
    bench = run_proxy_backtest(
        history,
        lambda _h, **_k: ({SAFE_HAVEN: 1.0}, {}),
        config=ProxyBacktestConfig(min_history_days=252),
        universe_symbols=(SAFE_HAVEN,),
    )
    bench_returns = bench.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    return {
        "profile": CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
        "universe_mode": universe_mode,
        "universe_size": len(universe),
        "overall": overall,
        "510300_from_dividend_data": compute_backtest_metrics(bench_returns.dropna()),
        "periods": {
            "bear_2021_2022": _metrics_slice(returns, "2021-01-01", "2022-12-31"),
            "oos_2024_2026": _metrics_slice(returns, "2024-01-01", end),
        },
        "panel_diagnostics": panel_diag,
    }


def _score_candidate(row: dict[str, Any], *, mdd_budget: float) -> dict[str, Any]:
    overall = row["overall"]
    mdd = float(overall["max_drawdown"])
    ann = float(overall["annual_return"])
    within = mdd >= mdd_budget
    oos = row.get("periods", {}).get("oos_2024_2026", {})
    return {
        **row,
        "within_mdd_budget": within,
        "score_ann_within_budget": ann if within else float("-inf"),
        "oos_total_return": float(oos.get("total_return", 0.0)),
    }


def run_live_candidate_evaluation(*, start: str, end: str) -> dict[str, Any]:
    runtime_profiles = sorted(get_runtime_enabled_profiles())
    runtime_meta = {
        profile: {
            "display_name": get_strategy_metadata(profile).display_name,
            "status": get_strategy_metadata(profile).status,
            "description": get_strategy_metadata(profile).description,
        }
        for profile in runtime_profiles
    }

    etf_conservative = _etf_leg_metrics(
        start=start,
        end=end,
        profile=CN_INDUSTRY_ETF_ROTATION_PROFILE,
    )
    etf_aggressive = _etf_leg_metrics(
        start=start,
        end=end,
        profile=CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    )
    dividend_staging = _dividend_leg_metrics(start=start, end=end, universe_mode="staging")
    dividend_expanded = _dividend_leg_metrics(start=start, end=end, universe_mode="expanded")

    combo_conservative_expanded = run_dual_track_combo(
        start=start,
        end=end,
        industry_weight=0.70,
        dividend_weight=0.30,
        industry_profile="conservative",
        dividend_universe_mode="expanded",
    )
    combo_aggressive_expanded = run_dual_track_combo(
        start=start,
        end=end,
        industry_weight=0.70,
        dividend_weight=0.30,
        industry_profile="aggressive",
        dividend_universe_mode="expanded",
    )

    candidates: list[dict[str, Any]] = [
        {
            "candidate_id": "live_primary_etf_conservative",
            "kind": "single_leg",
            "live_ready": True,
            "qmt_target": "qmt/industry_etf_dry_run",
            "runtime_profile": CN_INDUSTRY_ETF_ROTATION_PROFILE,
            "overall": etf_conservative["overall"],
            "periods": etf_conservative["periods"],
            "notes": "Current QMT default; market_history input; e2e verified.",
        },
        {
            "candidate_id": "live_optional_etf_aggressive",
            "kind": "single_leg",
            "live_ready": False,
            "qmt_target": "qmt/industry_etf_aggressive_dry_run",
            "runtime_profile": CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
            "overall": etf_aggressive["overall"],
            "periods": etf_aggressive["periods"],
            "notes": "research_backtest_only; passed ETF promotion gate; +~1pp ann vs conservative.",
        },
        {
            "candidate_id": "live_snapshot_dividend_staging",
            "kind": "single_leg",
            "live_ready": True,
            "qmt_target": "qmt/dividend_quality_dry_run",
            "runtime_profile": CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
            "overall": dividend_staging["overall"],
            "periods": dividend_staging["periods"],
            "notes": "runtime_enabled; fixture e2e; staging universe smaller.",
        },
        {
            "candidate_id": "live_snapshot_dividend_expanded",
            "kind": "single_leg",
            "live_ready": "pipeline_ready",
            "qmt_target": "qmt/dividend_quality_dry_run + expanded snapshot path",
            "runtime_profile": CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
            "overall": dividend_expanded["overall"],
            "periods": dividend_expanded["periods"],
            "universe_mode": "expanded",
            "notes": "Same profile; expanded universe via CnEquitySnapshotPipelines metadata.",
        },
        {
            "candidate_id": "combo_70_30_conservative_expanded",
            "kind": "return_blend",
            "live_ready": False,
            "runtime_profile": f"{CN_INDUSTRY_ETF_ROTATION_PROFILE}+{CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE}",
            "overall": combo_conservative_expanded["full_sample"]["combo"],
            "periods": combo_conservative_expanded["periods"],
            "notes": "Not unified portfolio sim; best ann among combos in prior research.",
        },
        {
            "candidate_id": "combo_70_30_aggressive_expanded",
            "kind": "return_blend",
            "live_ready": False,
            "runtime_profile": f"{CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE}+{CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE}",
            "overall": combo_aggressive_expanded["full_sample"]["combo"],
            "periods": combo_aggressive_expanded["periods"],
            "notes": "Higher industry vol; long-sample ann lower than conservative combo in 2017+ run.",
        },
    ]

    recommendations: dict[str, Any] = {}
    for budget in MDD_BUDGETS:
        scored = [_score_candidate(row, mdd_budget=budget) for row in candidates]
        live_ready_scored = [
            row
            for row in scored
            if row.get("live_ready") is True and row["within_mdd_budget"]
        ]
        best_live_ann = (
            max(live_ready_scored, key=lambda row: row["score_ann_within_budget"])
            if live_ready_scored
            else None
        )
        best_any_ann = max(scored, key=lambda row: row["score_ann_within_budget"])
        recommendations[f"mdd_budget_{int(abs(budget) * 100)}pct"] = {
            "best_live_ready_by_ann": best_live_ann["candidate_id"] if best_live_ann else None,
            "best_overall_by_ann": best_any_ann["candidate_id"]
            if best_any_ann["within_mdd_budget"]
            else None,
        }

    return {
        "start": start,
        "end": end,
        "mdd_budgets": list(MDD_BUDGETS),
        "runtime_enabled_profiles": runtime_profiles,
        "runtime_metadata": runtime_meta,
        "research_only_profiles": [
            CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
            CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        ],
        "candidates": candidates,
        "recommendations": recommendations,
        "live_deployment_summary": {
            "primary_qmt_target": "qmt/industry_etf_dry_run",
            "secondary_qmt_target": "qmt/dividend_quality_dry_run",
            "proposed_optional_target": "qmt/industry_etf_aggressive_dry_run",
            "dual_track_live": "not yet — return blend only in research",
        },
    }


def _print_report(payload: dict[str, Any]) -> None:
    print("\n=== A 股 Live 候选评估（runtime + snapshot）===\n")
    print(f"Runtime enabled: {', '.join(payload['runtime_enabled_profiles'])}")
    print(f"区间: {payload['start']} ~ {payload['end']}\n")
    print(f"{'candidate_id':<42} {'live':<6} {'ann':>7} {'mdd':>8} {'oos':>8}")
    for row in payload["candidates"]:
        overall = row["overall"]
        oos = row.get("periods", {}).get("oos_2024_2026", {})
        live = "yes" if row.get("live_ready") is True else str(row.get("live_ready", "no"))
        print(
            f"{row['candidate_id']:<42} {live:<6} "
            f"{overall['annual_return']:7.2%} {overall['max_drawdown']:8.2%} "
            f"{oos.get('total_return', 0.0):+8.2%}"
        )
    print("\nRecommendations:")
    for key, rec in payload["recommendations"].items():
        print(
            f"  {key}: live_ready={rec['best_live_ready_by_ann']} | "
            f"best_any={rec['best_overall_by_ann']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Live candidate evaluation for CN strategies.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run_live_candidate_evaluation(start=args.start, end=args.end)
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
