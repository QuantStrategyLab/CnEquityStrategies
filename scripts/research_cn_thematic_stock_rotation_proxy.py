#!/usr/bin/env python3
"""Thematic stock rotation proxy (optical/CPO/compute sleeve) — research only."""

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

from cn_equity_strategies.backtest.promotion_gate import evaluate_promotion  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    CONSERVATIVE_V1_PRESET,
    OPTICAL_COMPUTE_STOCK_SYMBOLS,
    STOCK_THEMATIC_PRESETS,
    STOCK_THEMATIC_PROMOTION_GATE,
    STOCK_THEMATIC_RESEARCH_MATRIX,
    STOCK_THEMATIC_RISK_PRESETS,
)
from research_cn_industry_etf_rotation_aggressive_matrix import (  # noqa: E402
    _run_preset,
)
from research_cn_industry_etf_rotation_validation import (  # noqa: E402
    VALIDATION_PERIODS,
)

_ETF_SYMBOL_PREFIXES = ("51", "15", "58")


def _is_etf_symbol(symbol: str) -> bool:
    normalized = str(symbol).strip()
    return normalized.startswith(_ETF_SYMBOL_PREFIXES)


def _symbols_for_presets(presets: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    symbols: list[str] = []
    for preset in presets.values():
        symbols.extend(str(item) for item in preset.get("universe_symbols") or ())
        symbols.extend(str(item) for item in preset.get("defensive_symbols") or ())
        benchmark = preset.get("benchmark_symbol")
        if benchmark:
            symbols.append(str(benchmark))
    return tuple(dict.fromkeys(symbols))


def _download_thematic_history(*, symbols: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    rows: list[dict[str, object]] = []
    for symbol in symbols:
        if _is_etf_symbol(symbol):
            frame = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adjust="qfq",
            )
            if frame is None or frame.empty:
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
            continue
        frame = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if frame is None or frame.empty:
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
    if output.empty:
        return output
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _active_symbols_at_start(
    market_history: pd.DataFrame,
    *,
    candidates: tuple[str, ...],
    start: str,
    min_rows: int = 220,
) -> tuple[str, ...]:
    start_ts = pd.Timestamp(start)
    active: list[str] = []
    for symbol in candidates:
        if _is_etf_symbol(symbol):
            continue
        frame = market_history.loc[market_history["symbol"] == symbol].sort_values("date")
        if frame.empty:
            continue
        first_date = pd.Timestamp(frame["date"].iloc[0])
        rows_before_end = frame.loc[frame["date"] >= start_ts]
        if first_date <= start_ts + pd.Timedelta(days=90) and len(rows_before_end) >= int(min_rows):
            active.append(symbol)
    return tuple(active)


def _select_presets(suite: str) -> dict[str, dict[str, Any]]:
    if suite == "stock_risk":
        return dict(STOCK_THEMATIC_RISK_PRESETS)
    if suite == "stock":
        return dict(STOCK_THEMATIC_PRESETS)
    return dict(STOCK_THEMATIC_RESEARCH_MATRIX)


def run_stock_thematic_matrix(*, start: str, end: str, suite: str = "stock") -> dict[str, Any]:
    preset_source = _select_presets(suite)
    download_symbols = _symbols_for_presets(preset_source)
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    raw = _download_thematic_history(symbols=download_symbols, start=download_start, end=end)
    active = _active_symbols_at_start(
        raw,
        candidates=OPTICAL_COMPUTE_STOCK_SYMBOLS,
        start=start,
        min_rows=220,
    )
    if len(active) < 3:
        raise ValueError(f"insufficient active optical/compute symbols at {start}: {active}")

    def _preset_universe(preset: dict[str, Any]) -> tuple[str, ...]:
        universe = tuple(str(item) for item in preset.get("universe_symbols") or ())
        stock_names = {symbol for symbol in universe if not _is_etf_symbol(symbol)}
        if not stock_names:
            return universe
        if stock_names.issubset(set(active)):
            return universe
        etf_names = tuple(symbol for symbol in universe if _is_etf_symbol(symbol))
        return tuple(dict.fromkeys([*active, *etf_names]))

    presets = {
        key: {**preset, "universe_symbols": _preset_universe(preset)}
        for key, preset in preset_source.items()
    }
    history_symbols = _symbols_for_presets(presets)
    market_history = raw.loc[raw["symbol"].isin(history_symbols)].copy()
    results = {key: _run_preset(market_history, key, preset) for key, preset in presets.items()}

    from research_cn_industry_etf_rotation_validation import _download_market_history

    etf_history = _download_market_history(start=download_start, end=end)
    conservative = _run_preset(etf_history, "conservative_v1", CONSERVATIVE_V1_PRESET)
    promotion = evaluate_promotion(
        {"conservative_v1": conservative, **results},
        STOCK_THEMATIC_PROMOTION_GATE,
    )

    return {
        "start": start,
        "end": end,
        "suite": suite,
        "status": "research_only",
        "active_symbols": list(active),
        "candidate_symbols": list(OPTICAL_COMPUTE_STOCK_SYMBOLS),
        "conservative_etf_baseline": conservative,
        "variants": results,
        "promotion_review": promotion,
        "promotion_gate": STOCK_THEMATIC_PROMOTION_GATE,
        "limitations": [
            "fixed optical/compute stock list (survivorship / theme hindsight)",
            "requires overlapping listing history; universe shrinks to active names at start",
            "not runtime-enabled; stricter gate vs ETF conservative_v1",
            "risk presets may include ETF benchmark symbols (510300/512760) for risk-off",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    title = "光模块/算力 个股主题轮动 — research proxy"
    if payload.get("suite") == "stock_risk":
        title += " (risk-control matrix)"
    print(f"\n=== {title} ===\n")
    print(f"active symbols ({len(payload['active_symbols'])}): {', '.join(payload['active_symbols'])}")
    base = payload["conservative_etf_baseline"]["overall"]
    print(
        f"ETF conservative v1 reference: ann={base['annual_return']:.2%} "
        f"total={base['total_return']:.2%} mdd={base['max_drawdown']:.2%}"
    )
    print()
    rows = sorted(payload["variants"].values(), key=lambda item: item["overall"]["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        print(
            f"{index:2}. {row['label']:<52} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )
    print("\n=== vs ETF conservative v1 (stock thematic gate) ===")
    for item in payload["promotion_review"]["candidates"]:
        flag = "PASS" if item["passes_gate"] else "fail"
        reasons = ",".join(item.get("fail_reasons") or []) or "-"
        print(
            f"  [{flag}] {item['key']:<34} oos_lift={item['oos_total_return_lift']:+7.2%} "
            f"mdd={item['overall_mdd']:7.2%} bear={item.get('bear_vs_baseline')} reasons={reasons}"
        )
    print("\n分阶段 total_return (best stock variant vs ETF conservative):")
    if not rows:
        return
    best = rows[0]
    etf = payload["conservative_etf_baseline"]
    for period in ("bear_2021_2022", "theme_2024_2025", "oos_2024_2026"):
        if period not in VALIDATION_PERIODS:
            continue
        stock_metric = best["period_metrics"].get(period, {})
        etf_metric = etf["period_metrics"].get(period, {})
        if int(stock_metric.get("days", 0)) <= 0:
            continue
        print(
            f"  {period:<16} stock={stock_metric['total_return']:+7.2%} "
            f"etf={etf_metric.get('total_return', 0.0):+7.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Optical/compute stock thematic rotation research proxy.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument(
        "--suite",
        choices=("stock", "stock_risk", "all"),
        default="stock",
        help="stock=baseline presets; stock_risk=defensive parameter matrix; all=full matrix",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    suite = "stock" if args.suite == "all" else args.suite
    if args.suite == "all":
        baseline = run_stock_thematic_matrix(start=args.start, end=args.end, suite="stock")
        risk = run_stock_thematic_matrix(start=args.start, end=args.end, suite="stock_risk")
        payload = {
            "start": args.start,
            "end": args.end,
            "suite": "all",
            "baseline": baseline,
            "risk_control": risk,
        }
    else:
        payload = run_stock_thematic_matrix(start=args.start, end=args.end, suite=suite)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    if args.suite == "all":
        _print_report(baseline)
        _print_report(risk)
    else:
        _print_report(payload)


if __name__ == "__main__":
    main()
