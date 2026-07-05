#!/usr/bin/env python3
"""科创板增强版 research 骨架。

这不是 runtime 版本，也不是 live 候选。用途只有一个：
先把科创板从“窄池挑最强”切到“板块增强 + 风控”研究框架里。
"""

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

from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    compute_backtest_metrics,
    run_proxy_backtest,
)
from cn_equity_strategies.research.momentum_stock_history import download_symbol_histories  # noqa: E402
from research_cn_industry_etf_rotation_aggressive_matrix import _run_preset  # noqa: E402
from research_cn_industry_etf_rotation_validation import _download_market_history  # noqa: E402

KCB_CODE_PREFIXES = ("688", "689")
DEFAULT_BENCHMARK_SYMBOL = "510300"

# 这版先只给研究骨架，不做复杂 PIT 过滤。
KCB_RESEARCH_PRESETS: dict[str, dict[str, Any]] = {
    "kcb_enhanced_monthly_top5_vol20": {
        "label": "STAR board enhanced — monthly top5 vol20%",
        "universe_mode": "kcb",
        "top_n": 5,
        "target_annual_volatility": 0.20,
        "rebalance_frequency": "monthly",
        "sentiment_mode": "off",
        "benchmark_symbol": DEFAULT_BENCHMARK_SYMBOL,
        "defensive_symbols": ("510300",),
    },
    "kcb_enhanced_monthly_top5_vol18": {
        "label": "STAR board enhanced — monthly top5 vol18%",
        "universe_mode": "kcb",
        "top_n": 5,
        "target_annual_volatility": 0.18,
        "rebalance_frequency": "monthly",
        "sentiment_mode": "off",
        "benchmark_symbol": DEFAULT_BENCHMARK_SYMBOL,
        "defensive_symbols": ("510300",),
    },
    "kcb_enhanced_monthly_top8_vol18": {
        "label": "STAR board enhanced — monthly top8 vol18%",
        "universe_mode": "kcb",
        "top_n": 8,
        "target_annual_volatility": 0.18,
        "rebalance_frequency": "monthly",
        "sentiment_mode": "off",
        "benchmark_symbol": DEFAULT_BENCHMARK_SYMBOL,
        "defensive_symbols": ("510300",),
    },
}


def _load_shanghai_stock_table() -> pd.DataFrame:
    import akshare as ak

    frame = ak.stock_info_sh_name_code()
    if frame is None or frame.empty:
        raise RuntimeError("stock_info_sh_name_code returned no data")
    output = frame.copy()
    output["symbol"] = output["证券代码"].astype(str).str.zfill(6)
    output["name"] = output["证券简称"].astype(str)
    output["list_date"] = pd.to_datetime(output["上市日期"], errors="coerce").dt.normalize()
    return output


def _resolve_kcb_universe(*, start: str, top_n: int = 120) -> tuple[str, ...]:
    frame = _load_shanghai_stock_table()
    start_ts = pd.Timestamp(start).normalize()
    frame = frame.loc[
        frame["symbol"].str.startswith(KCB_CODE_PREFIXES)
        & frame["list_date"].notna()
        & (frame["list_date"] <= start_ts)
        & ~frame["name"].str.contains("ST", case=False, na=False)
    ].copy()
    frame = frame.sort_values(["list_date", "symbol"], ascending=[True, True])
    symbols = tuple(dict.fromkeys(frame["symbol"].head(int(top_n)).tolist()))
    if len(symbols) < 10:
        raise ValueError(f"KCB universe too small after filtering: {len(symbols)}")
    return symbols


def _download_kcb_history(*, symbols: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame = download_symbol_histories((symbol,), start=start, end=end)
        if frame is None or frame.empty:
            continue
        rows.extend(frame.to_dict(orient="records"))
    output = pd.DataFrame(rows)
    if output.empty:
        return output
    output["date"] = pd.to_datetime(output["date"], utc=False).dt.tz_localize(None).dt.normalize()
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)


def _run_kcb_preset(market_history: pd.DataFrame, key: str, preset: dict[str, Any]) -> dict[str, Any]:
    runtime_preset = {
        key_: value
        for key_, value in preset.items()
        if key_ not in {"universe_mode", "label"}
    }
    runtime_preset["universe_symbols"] = tuple(dict.fromkeys(runtime_preset.get("universe_symbols") or ()))
    if not runtime_preset["universe_symbols"]:
        raise ValueError("runtime_preset must contain universe_symbols")
    return _run_preset(market_history, key, runtime_preset)


def run(*, start: str, end: str, top_n: int = 120) -> dict[str, Any]:
    download_start = (pd.Timestamp(start) - pd.Timedelta(days=450)).date().isoformat()
    universe = _resolve_kcb_universe(start=start, top_n=top_n)
    stock_history = _download_kcb_history(symbols=universe, start=download_start, end=end)
    benchmark_history = _download_market_history(start=download_start, end=end)
    market_history = pd.concat([stock_history, benchmark_history], ignore_index=True)
    if market_history.empty:
        raise ValueError("KCB market history is empty")

    # 研究骨架：当前先把 KCB 线跑成和现有 momentum / tactical 统一的 proxy 形状。
    # 后续要把 growth/quality 因子和更严格的 PIT 接进来，再判断是否值得继续做 live 级设计。
    results = {
        key: _run_kcb_preset(market_history, key, {**preset, "universe_symbols": universe})
        for key, preset in KCB_RESEARCH_PRESETS.items()
    }

    benchmark = run_proxy_backtest(
        benchmark_history.loc[benchmark_history["symbol"] == DEFAULT_BENCHMARK_SYMBOL].copy(),
        lambda _h, **_k: ({DEFAULT_BENCHMARK_SYMBOL: 1.0}, {"label": DEFAULT_BENCHMARK_SYMBOL}),
        config=ProxyBacktestConfig(min_history_days=220),
        universe_symbols=(DEFAULT_BENCHMARK_SYMBOL,),
    )

    return {
        "start": start,
        "end": end,
        "track": "kcb_enhanced",
        "status": "research_backtest_only",
        "universe": {
            "mode": "kcb_code_prefix_688_689",
            "size": len(universe),
            "top_n": top_n,
            "sample": list(universe[:12]),
        },
        "data_rows": int(len(market_history)),
        "benchmark": compute_backtest_metrics(benchmark.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()),
        "variants": results,
        "limitations": [
            "universe currently uses SH code prefixes 688/689; not full PIT KCB membership",
            "factor logic is still tactical proxy style; growth/quality enhancement not yet wired",
            "no runtime registration; research only",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    print("\n=== 科创板增强版 research 骨架 ===\n")
    print(
        f"Universe: mode={payload['universe']['mode']} size={payload['universe']['size']} "
        f"top_n={payload['universe']['top_n']} sample={', '.join(payload['universe']['sample'])}"
    )
    benchmark = payload["benchmark"]
    print(
        f"Benchmark ann={benchmark['annual_return']:.2%} total={benchmark['total_return']:.2%} "
        f"mdd={benchmark['max_drawdown']:.2%}"
    )
    rows = sorted(payload["variants"].values(), key=lambda item: item["overall"]["annual_return"], reverse=True)
    for index, row in enumerate(rows, start=1):
        overall = row["overall"]
        print(
            f"{index:2}. {row['label']:<52} "
            f"ann={overall['annual_return']:6.2%} mdd={overall['max_drawdown']:7.2%} "
            f"total={overall['total_return']:7.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Research skeleton for KCB enhanced strategy.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--top-n", type=int, default=120)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    payload = run(start=args.start, end=args.end, top_n=args.top_n)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    _print_report(payload)


if __name__ == "__main__":
    main()
