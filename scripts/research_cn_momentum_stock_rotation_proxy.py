#!/usr/bin/env python3
"""Cross-sectional A-share momentum stock rotation — research proxy (宽池 + 动量 top-N)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for candidate in (SRC, SCRIPTS):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion  # noqa: E402
from cn_equity_strategies.research.momentum_stock_history import (  # noqa: E402
    BENCHMARK_SYMBOL,
    active_stock_symbols_at_start,
    download_symbol_histories,
)
from cn_equity_strategies.research.momentum_stock_universe import (  # noqa: E402
    resolve_momentum_stock_universe,
)
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    CONSERVATIVE_V1_PRESET,
    OPTICAL_COMPUTE_STOCK_SYMBOLS,
    STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS,
    STOCK_MOMENTUM_CROSS_SECTION_PRESETS,
    STOCK_MOMENTUM_PROMOTION_GATE,
)
from research_cn_industry_etf_rotation_aggressive_matrix import _run_preset  # noqa: E402
from research_cn_industry_etf_rotation_validation import _download_market_history  # noqa: E402

ResearchTrack = Literal["momentum", "thematic", "both"]


def _extra_symbols_for_preset(preset: dict[str, Any]) -> tuple[str, ...]:
    extras: list[str] = []
    extras.extend(str(item) for item in preset.get("defensive_symbols") or ())
    benchmark = preset.get("benchmark_symbol")
    if benchmark:
        extras.append(str(benchmark))
    return tuple(dict.fromkeys(extras))


def _materialize_preset(
    preset: dict[str, Any],
    *,
    stock_universe: tuple[str, ...],
) -> dict[str, Any]:
    runtime = {
        key: value
        for key, value in preset.items()
        if key not in {"universe_mode", "liquid_top_n"}
    }
    runtime["universe_symbols"] = tuple(dict.fromkeys([*stock_universe, *_extra_symbols_for_preset(preset)]))
    return runtime


def _select_presets(
    *,
    universe_mode: str | None,
    preset_keys: tuple[str, ...] | None,
    suite: str | None = None,
) -> dict[str, dict[str, Any]]:
    if suite == "csi500_riskoff":
        return dict(STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS)
    if preset_keys:
        missing = [key for key in preset_keys if key not in STOCK_MOMENTUM_CROSS_SECTION_PRESETS]
        if missing:
            raise ValueError(f"unknown momentum preset keys: {missing}")
        return {key: STOCK_MOMENTUM_CROSS_SECTION_PRESETS[key] for key in preset_keys}
    if universe_mode:
        selected = {
            key: preset
            for key, preset in STOCK_MOMENTUM_CROSS_SECTION_PRESETS.items()
            if str(preset.get("universe_mode")) == universe_mode
        }
        if not selected:
            raise ValueError(f"no presets for universe_mode={universe_mode!r}")
        return selected
    return dict(STOCK_MOMENTUM_CROSS_SECTION_PRESETS)


def _universe_cache_key(preset: dict[str, Any]) -> tuple[str, int]:
    return (str(preset["universe_mode"]), int(preset.get("liquid_top_n") or 300))


def _load_universe_bundle(
    preset: dict[str, Any],
    *,
    download_start: str,
    end: str,
    start: str,
    max_symbols: int | None,
) -> tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...]]:
    mode = str(preset["universe_mode"])
    liquid_top_n = int(preset.get("liquid_top_n") or 300)
    candidate_universe = resolve_momentum_stock_universe(mode, liquid_top_n=liquid_top_n)  # type: ignore[arg-type]
    if max_symbols is not None:
        candidate_universe = candidate_universe[: int(max_symbols)]
    extras = _extra_symbols_for_preset(preset)
    download_symbols = tuple(dict.fromkeys([*candidate_universe, *extras, BENCHMARK_SYMBOL]))
    history = download_symbol_histories(download_symbols, start=download_start, end=end)
    active = active_stock_symbols_at_start(
        history,
        candidates=candidate_universe,
        start=start.split("T")[0],
        min_rows=220,
    )
    keep = tuple(dict.fromkeys([*active, *extras]))
    filtered = history.loc[history["symbol"].isin(keep)].copy()
    return filtered, candidate_universe, active


def run_momentum_stock_matrix(
    *,
    start: str,
    end: str,
    universe_mode: str | None = "csi500",
    preset_keys: tuple[str, ...] | None = None,
    max_symbols: int | None = None,
    suite: str | None = None,
) -> dict[str, Any]:
    preset_source = _select_presets(universe_mode=universe_mode, preset_keys=preset_keys, suite=suite)
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()

    results: dict[str, dict[str, Any]] = {}
    universe_diagnostics: dict[str, Any] = {}
    history_cache: dict[tuple[str, int], tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...]]] = {}

    for key, preset in preset_source.items():
        cache_key = _universe_cache_key(preset)
        if cache_key not in history_cache:
            history_cache[cache_key] = _load_universe_bundle(
                preset,
                download_start=download_start,
                end=end,
                start=start,
                max_symbols=max_symbols,
            )
        market_history, candidate_universe, active = history_cache[cache_key]
        if len(active) < (40 if max_symbols is not None else 80):
            raise ValueError(
                f"{key}: insufficient active symbols at {start} ({len(active)}); "
                f"try smaller universe or later start date"
            )
        runtime_preset = _materialize_preset(preset, stock_universe=active)
        results[key] = _run_preset(market_history, key, runtime_preset)
        universe_diagnostics[key] = {
            "universe_mode": preset.get("universe_mode"),
            "candidate_count": len(candidate_universe),
            "active_count": len(active),
            "sample_active": list(active[:12]),
        }

    etf_history = _download_market_history(start=download_start, end=end)
    conservative = _run_preset(etf_history, "conservative_v1", CONSERVATIVE_V1_PRESET)
    promotion = evaluate_promotion(
        {"conservative_v1": conservative, **results},
        STOCK_MOMENTUM_PROMOTION_GATE,
    )

    return {
        "start": start,
        "end": end,
        "track": "cross_section_momentum_riskoff" if suite == "csi500_riskoff" else "cross_section_momentum",
        "status": "research_only",
        "default_universe_mode": suite or universe_mode or "all_presets",
        "conservative_etf_baseline": conservative,
        "variants": results,
        "promotion_review": promotion,
        "promotion_gate": STOCK_MOMENTUM_PROMOTION_GATE,
        "universe_diagnostics": universe_diagnostics,
        "limitations": [
            "index constituents (CSI500/1000) use latest csindex table — not fully point-in-time",
            "liquid_top uses current spot turnover snapshot — not historical liquidity PIT",
            "selection is cross-sectional momentum within broad pool, not fixed thematic industry list",
            "not runtime-enabled; compare vs ETF conservative_v1 and thematic 8-name sleeve separately",
        ],
    }


def run_thematic_reference(*, start: str, end: str) -> dict[str, Any]:
    from research_cn_thematic_stock_rotation_proxy import run_stock_thematic_matrix

    payload = run_stock_thematic_matrix(start=start, end=end, suite="stock")
    payload["track"] = "fixed_thematic_sleeve"
    payload["reference_symbols"] = list(OPTICAL_COMPUTE_STOCK_SYMBOLS)
    return payload


def _print_momentum_report(payload: dict[str, Any]) -> None:
    print("\n=== A 股 cross-section 动量个股轮动 — research proxy ===\n")
    diag = payload.get("universe_diagnostics") or {}
    if diag:
        first = next(iter(diag.values()))
        print(
            f"universe_mode={payload.get('default_universe_mode')} | "
            f"active≈{first.get('active_count')} / candidate≈{first.get('candidate_count')}"
        )
    base = payload["conservative_etf_baseline"]["overall"]
    print(
        f"ETF conservative v1 reference: ann={base['annual_return']:.2%} "
        f"total={base['total_return']:.2%} mdd={base['max_drawdown']:.2%}"
    )
    print()
    rows = sorted(payload["variants"].values(), key=lambda item: item["overall"]["annual_return"], reverse=True)
    if payload.get("track") == "cross_section_momentum_riskoff":
        rows = sorted(
            payload["variants"].values(),
            key=lambda item: (item["overall"]["max_drawdown"], -item["overall"]["annual_return"]),
            reverse=True,
        )
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        print(
            f"{index:2}. {row['label']:<58} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print("\n=== vs ETF conservative v1 (momentum stock gate) ===")
    promoted = {item["key"] for item in payload["promotion_review"].get("promoted") or []}
    for item in payload["promotion_review"]["candidates"]:
        flag = "PASS" if item["passes_gate"] else "fail"
        reasons = ",".join(item.get("fail_reasons") or []) or "-"
        print(
            f"  [{flag}] {item['key']:<36} oos_lift={item['oos_total_return_lift']:+7.2%} "
            f"mdd={item['overall_mdd']:7.2%} bearΔ={item.get('bear_vs_baseline')} reasons={reasons}"
        )
    if promoted:
        print("\nPromoted variants:", ", ".join(sorted(promoted)))
    if not rows:
        return
    best = rows[0]
    etf = payload["conservative_etf_baseline"]
    print("\n分阶段 total_return (best momentum vs ETF conservative):")
    for period in ("bear_2021_2022", "oos_2024_2026", "full"):
        stock_metric = best["period_metrics"].get(period, {})
        etf_metric = etf["period_metrics"].get(period, {})
        if int(stock_metric.get("days", 0)) <= 0:
            continue
        print(
            f"  {period:<16} stock={stock_metric['total_return']:+7.2%} "
            f"etf={etf_metric.get('total_return', 0.0):+7.2%}"
        )


def _print_comparison(momentum: dict[str, Any], thematic: dict[str, Any]) -> None:
    print("\n=== 轨道对照：cross-section 动量 vs 固定主题 8 股 ===")
    etf_ann = momentum["conservative_etf_baseline"]["overall"]["annual_return"]
    mom_best = max(momentum["variants"].values(), key=lambda row: row["overall"]["annual_return"])
    them_best = max(thematic["variants"].values(), key=lambda row: row["overall"]["annual_return"])
    print(
        f"ETF conservative ann={etf_ann:.2%} | "
        f"momentum best ({mom_best['key']}) ann={mom_best['overall']['annual_return']:.2%} "
        f"mdd={mom_best['overall']['max_drawdown']:.2%} | "
        f"thematic best ({them_best['key']}) ann={them_best['overall']['annual_return']:.2%} "
        f"mdd={them_best['overall']['max_drawdown']:.2%}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-section momentum stock rotation research proxy.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument(
        "--universe-mode",
        choices=("csi500", "csi1000", "liquid_top", "all"),
        default="csi500",
        help="Default CSI500; all=run every cross-section preset (slow)",
    )
    parser.add_argument(
        "--suite",
        choices=("momentum", "thematic", "both", "csi500_riskoff"),
        default="momentum",
        help="momentum=default csi500 presets; csi500_riskoff=CSI500 risk-off tuning matrix",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Optional cap on downloaded index constituents (dev/smoke only)",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    universe_mode = None if args.universe_mode == "all" else args.universe_mode
    momentum_payload = None
    thematic_payload = None
    run_riskoff = args.suite == "csi500_riskoff"
    run_momentum = args.suite in {"momentum", "both", "csi500_riskoff"}

    if run_momentum:
        momentum_payload = run_momentum_stock_matrix(
            start=args.start,
            end=args.end,
            universe_mode=universe_mode if not run_riskoff else "csi500",
            max_symbols=args.max_symbols,
            suite="csi500_riskoff" if run_riskoff else None,
        )
        _print_momentum_report(momentum_payload)
    if args.suite in {"thematic", "both"}:
        thematic_payload = run_thematic_reference(start=args.start, end=args.end)
        from research_cn_thematic_stock_rotation_proxy import _print_report

        _print_report(thematic_payload)
    if momentum_payload and thematic_payload:
        _print_comparison(momentum_payload, thematic_payload)

    output = {
        "start": args.start,
        "end": args.end,
        "suite": args.suite,
        "momentum": momentum_payload,
        "thematic_reference": thematic_payload,
    }
    if args.json_output:
        args.json_output.write_text(json.dumps(output, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
