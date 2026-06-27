#!/usr/bin/env python3
"""Research matrix: conservative v1 baseline vs aggressive industry rotation variants."""

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
for candidate in (SRC, SCRIPTS):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest  # noqa: E402
from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion  # noqa: E402
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_rotation  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    AGGRESSIVE_RESEARCH_PRESETS,
    CONSERVATIVE_V1_PRESET,
    PROMOTION_GATE,
)
from research_cn_industry_etf_rotation_validation import (  # noqa: E402
    VALIDATION_PERIODS,
    _download_market_history,
    _period_metrics,
)


def _run_preset(market_history, key: str, preset: dict[str, Any]) -> dict[str, Any]:
    rebalance_frequency = str(preset.get("rebalance_frequency") or "monthly")
    config = ProxyBacktestConfig(
        min_history_days=int(preset.get("min_history_days") or industry_rotation.DEFAULT_MIN_HISTORY_DAYS),
        rebalance_frequency=rebalance_frequency,  # type: ignore[arg-type]
    )
    strategy_kwargs = {
        key: value
        for key, value in preset.items()
        if key
        not in {
            "profile_variant",
            "label",
            "rebalance_frequency",
            "execution_cash_reserve_ratio",
        }
    }

    def signal_fn(history: Any, **kwargs: Any):
        merged = {**kwargs, **strategy_kwargs}
        return industry_rotation.build_target_weights(history, **merged)

    backtest = run_proxy_backtest(
        market_history,
        signal_fn,
        config=config,
        universe_symbols=tuple(preset["universe_symbols"]),
        strategy_kwargs=strategy_kwargs,
    )
    period_metrics = {
        period: _period_metrics(backtest.daily_returns, start, end)
        for period, (start, end) in VALIDATION_PERIODS.items()
    }
    return {
        "key": key,
        "label": preset.get("label", key),
        "profile_variant": preset.get("profile_variant"),
        "overall": backtest.metrics,
        "period_metrics": period_metrics,
        "rebalance_count": len(backtest.rebalance_events),
    }


def run_matrix(*, start: str, end: str, suite: str = "etf") -> dict[str, Any]:
    if suite in {"stock", "stock_risk"}:
        from research_cn_thematic_stock_rotation_proxy import run_stock_thematic_matrix

        return run_stock_thematic_matrix(start=start, end=end, suite=suite)

    if suite in {"momentum_stock", "stock_momentum"}:
        from research_cn_momentum_stock_rotation_proxy import run_momentum_stock_matrix

        return run_momentum_stock_matrix(start=start, end=end, universe_mode="csi500")

    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    market_history = _download_market_history(start=download_start, end=end)
    presets = {"conservative_v1": CONSERVATIVE_V1_PRESET, **AGGRESSIVE_RESEARCH_PRESETS}
    results = {key: _run_preset(market_history, key, preset) for key, preset in presets.items()}
    promotion = evaluate_promotion(results, PROMOTION_GATE)
    return {
        "start": start,
        "end": end,
        "suite": suite,
        "status": "research_only",
        "conservative_baseline": "conservative_v1",
        "variants": results,
        "promotion_review": promotion,
    }


def _print_report(payload: dict[str, Any]) -> None:
    if payload.get("active_symbols") is not None:
        from research_cn_thematic_stock_rotation_proxy import _print_report as _print_stock_report

        _print_stock_report(payload)
        return

    print("\n=== 行业 ETF 轮动 — Conservative v1 vs Aggressive research ===\n")
    rows = sorted(payload["variants"].values(), key=lambda item: item["overall"]["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        marker = "*" if row["key"] == "conservative_v1" else " "
        print(
            f"{index:2}.{marker} {row['label']:<44} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print("\n=== Promotion gate (OOS 2024–2026 vs conservative v1) ===")
    for item in payload["promotion_review"]["candidates"]:
        flag = "PASS" if item["passes_gate"] else "fail"
        print(
            f"  [{flag}] {item['key']:<28} oos_lift={item['oos_total_return_lift']:+7.2%} "
            f"mdd_delta={item['mdd_vs_baseline']:+.2%}"
        )
    promoted = payload["promotion_review"]["promoted"]
    if promoted:
        print("\nCandidates passing gate:", ", ".join(item["key"] for item in promoted))
    else:
        print("\nNo aggressive variant passed promotion gate yet.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative v1 vs aggressive industry rotation matrix.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--suite", choices=("etf", "stock", "stock_risk", "momentum_stock", "stock_momentum"), default="etf")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run_matrix(start=args.start, end=args.end, suite=args.suite)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    _print_report(payload)


if __name__ == "__main__":
    main()
