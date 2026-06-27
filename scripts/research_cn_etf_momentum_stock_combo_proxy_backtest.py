#!/usr/bin/env python3
"""Combo proxy: industry ETF rotation + CSI500 momentum stock risk-off sleeve."""

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

from cn_equity_strategies.backtest.proxy_simulator import (  # noqa: E402
    ProxyBacktestConfig,
    compute_backtest_metrics,
    run_proxy_backtest,
)
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_rotation  # noqa: E402
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_aggressive_rotation  # noqa: E402
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (  # noqa: E402
    CSI500_RISKOFF_MDD_OPTIMIZED_PRESET_KEY,
    STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS,
)
from research_cn_dual_track_combo_proxy_backtest import _combine_daily_returns  # noqa: E402
from research_cn_momentum_stock_rotation_proxy import (  # noqa: E402
    _load_universe_bundle,
    _materialize_preset,
)
from research_cn_us_long_horizon_comparison import (  # noqa: E402
    CN_BENCHMARK,
    CN_UNIVERSE_FULL,
    _download_cn_history,
    _metrics_slice,
    _run_cn_rotation,
    _window_with_warmup,
)

DEFAULT_ETF_WEIGHT = 0.70
DEFAULT_STOCK_WEIGHT = 0.30


def _periods_for_end(end: str) -> dict[str, tuple[str, str]]:
    return {
        "full": ("2021-01-01", end),
        "bear_2021_2022": ("2021-01-01", "2022-12-31"),
        "oos_2024_2026": ("2024-01-01", end),
        "2023_2026": ("2023-01-01", end),
    }


def _run_preset_daily_returns(market_history: Any, preset: dict[str, Any]) -> pd.Series:
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
            "universe_mode",
            "liquid_top_n",
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
    return backtest.daily_returns


def _metrics_from_returns(daily_returns: pd.Series) -> dict[str, float | int]:
    return compute_backtest_metrics(daily_returns.dropna())


def run_etf_momentum_stock_combo(
    *,
    start: str,
    end: str,
    etf_weight: float = DEFAULT_ETF_WEIGHT,
    stock_weight: float = DEFAULT_STOCK_WEIGHT,
    industry_profile: str = "conservative",
    stock_preset_key: str = CSI500_RISKOFF_MDD_OPTIMIZED_PRESET_KEY,
) -> dict[str, Any]:
    if stock_preset_key not in STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS:
        raise ValueError(f"unknown stock preset: {stock_preset_key}")

    download_start = (pd.Timestamp(start) - pd.Timedelta(days=400)).date().isoformat()
    target_vol = (
        float(industry_aggressive_rotation.DEFAULT_TARGET_ANNUAL_VOLATILITY)
        if industry_profile == "aggressive"
        else 0.20
    )

    industry_history = _download_cn_history(start=download_start, end=end)
    industry_window = _window_with_warmup(industry_history, start, end)
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

    stock_preset = STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS[stock_preset_key]
    stock_history, candidate_universe, active = _load_universe_bundle(
        stock_preset,
        download_start=download_start,
        end=end,
        start=start,
        max_symbols=None,
    )
    if len(active) < 80:
        raise ValueError(f"insufficient active CSI500 symbols at {start}: {len(active)}")
    stock_runtime = _materialize_preset(stock_preset, stock_universe=active)
    stock_returns = _run_preset_daily_returns(stock_history, stock_runtime)

    etf_slice = industry_result.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    stock_slice = stock_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    combo_slice = _combine_daily_returns(
        etf_slice,
        stock_slice,
        industry_weight=etf_weight,
        dividend_weight=stock_weight,
    )

    return {
        "start": start,
        "end": end,
        "weights": {
            "industry_etf": etf_weight,
            "momentum_stock": stock_weight,
        },
        "industry_profile": industry_profile,
        "industry_vol_target": target_vol,
        "stock_preset_key": stock_preset_key,
        "stock_preset_label": stock_preset.get("label"),
        "stock_universe": {
            "candidate_count": len(candidate_universe),
            "active_count": len(active),
            "sample_active": list(active[:12]),
        },
        "full_sample": {
            "combo": _metrics_from_returns(combo_slice),
            "industry_etf": _metrics_from_returns(etf_slice),
            "momentum_stock": _metrics_from_returns(stock_slice),
            "510300": _metrics_from_returns(
                industry_bench.daily_returns.loc[pd.Timestamp(start) : pd.Timestamp(end)]
            ),
        },
        "periods": {
            key: {
                "combo": _metrics_slice(combo_slice, pstart, pend),
                "industry_etf": _metrics_slice(etf_slice, pstart, pend),
                "momentum_stock": _metrics_slice(stock_slice, pstart, pend),
            }
            for key, (pstart, pend) in _periods_for_end(end).items()
        },
        "limitations": [
            "return-level blend (70/30) rather than unified multi-asset portfolio simulation",
            f"ETF leg profile={industry_profile} vol_target={target_vol:.0%}",
            f"stock leg preset={stock_preset_key}",
            "CSI500 constituents from latest csindex table — not fully PIT",
        ],
    }


def _print_report(payload: dict[str, Any]) -> None:
    weights = payload["weights"]
    print("\n========== 组合 proxy（行业 ETF + CSI500 动量 risk-off 个股）==========")
    print(
        f"权重: etf={weights['industry_etf']:.0%} | stock={weights['momentum_stock']:.0%} | "
        f"stock_preset={payload['stock_preset_key']}"
    )
    print(f"区间: {payload['start']} ~ {payload['end']}")
    full = payload["full_sample"]
    combo = full["combo"]
    etf = full["industry_etf"]
    stock = full["momentum_stock"]
    bench = full["510300"]
    print(
        f"组合       ann={combo['annual_return']:6.2%} total={combo['total_return']:7.2%} "
        f"mdd={combo['max_drawdown']:7.2%}"
    )
    print(
        f"行业ETF    ann={etf['annual_return']:6.2%} total={etf['total_return']:7.2%} "
        f"mdd={etf['max_drawdown']:7.2%}"
    )
    print(
        f"个股risk-off ann={stock['annual_return']:6.2%} total={stock['total_return']:7.2%} "
        f"mdd={stock['max_drawdown']:7.2%}"
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
            f"  {key:<16} combo={row['combo']['total_return']:+7.2%} "
            f"(ann {row['combo']['annual_return']:6.2%}) | "
            f"etf={row['industry_etf']['total_return']:+7.2%} | "
            f"stock={row['momentum_stock']['total_return']:+7.2%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ETF + momentum stock risk-off combo proxy.")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2026-06-27")
    parser.add_argument("--etf-weight", type=float, default=DEFAULT_ETF_WEIGHT)
    parser.add_argument("--stock-weight", type=float, default=DEFAULT_STOCK_WEIGHT)
    parser.add_argument(
        "--industry-profile",
        choices=("conservative", "aggressive"),
        default="conservative",
    )
    parser.add_argument(
        "--stock-preset",
        default=CSI500_RISKOFF_MDD_OPTIMIZED_PRESET_KEY,
        help="Key from STOCK_MOMENTUM_CSI500_RISKOFF_PRESETS",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    payload = run_etf_momentum_stock_combo(
        start=args.start,
        end=args.end,
        etf_weight=args.etf_weight,
        stock_weight=args.stock_weight,
        industry_profile=args.industry_profile,
        stock_preset_key=args.stock_preset,
    )
    _print_report(payload)
    if args.json_output:
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
