#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
for candidate in (SRC, QPK_SRC):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from quant_platform_kit.strategy_contracts import StrategyContext  # noqa: E402

from cn_equity_strategies import get_strategy_entrypoint  # noqa: E402
from cn_equity_strategies.catalog import CN_INDUSTRY_ETF_ROTATION_PROFILE  # noqa: E402
from cn_equity_strategies.runtime_adapters import describe_platform_runtime_requirements  # noqa: E402
from cn_equity_strategies.strategies.cn_industry_etf_rotation import (  # noqa: E402
    DEFAULT_UNIVERSE_SYMBOLS,
    extract_managed_symbols,
)

SYNTHETIC_AS_OF = "2026-02-25"


def build_synthetic_market_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rates = {
        "159819": 1.0010,
        "159995": 1.0009,
        "512760": 1.0008,
        "159994": 1.0007,
        "159852": 1.0006,
        "512170": 1.0004,
        "515030": 1.0009,
        "159792": 1.0005,
        "512800": 1.0003,
        "512690": 1.0002,
        "159928": 1.0001,
        "159915": 0.9998,
        "588000": 1.0000,
        "512100": 1.0003,
    }
    rows: list[dict[str, object]] = []
    for symbol in extract_managed_symbols():
        price = 20.0
        for idx, date in enumerate(dates):
            price *= rates.get(symbol, 1.0004)
            close = price * (1.0 + 0.04 * ((idx % 5) - 2) / 5)
            rows.append({"date": date, "symbol": symbol, "close": close, "volume": 1_000_000.0})
    return pd.DataFrame(rows)


def build_smoke_report() -> dict[str, object]:
    entrypoint = get_strategy_entrypoint(CN_INDUSTRY_ETF_ROTATION_PROFILE)
    decision = entrypoint.evaluate(
        StrategyContext(
            as_of=SYNTHETIC_AS_OF,
            market_data={"market_history": build_synthetic_market_history()},
            runtime_config={"min_history_days": 220, "sentiment_mode": "off"},
        )
    )
    target_weights = {
        position.symbol: float(position.target_weight or 0.0)
        for position in decision.positions
        if float(position.target_weight or 0.0) > 1e-12
    }
    gross_exposure = sum(target_weights.values())
    requirements = describe_platform_runtime_requirements(
        CN_INDUSTRY_ETF_ROTATION_PROFILE,
        platform_id="qmt",
    )
    managed = set(decision.diagnostics.get("managed_symbols") or ())
    checks = {
        "strategy_actionable": bool(decision.diagnostics.get("actionable")),
        "uses_direct_market_history": decision.diagnostics.get("signal_source") == "daily_market_history",
        "weights_non_empty": bool(target_weights),
        "gross_exposure_lte_one": 0.0 < gross_exposure <= 1.0,
        "qmt_direct_inputs": requirements["input_mode"] == "market_history",
        "pure_momentum_mode": decision.diagnostics.get("sentiment_mode") == "off",
        "excludes_global_gold": "513100" not in managed and "518880" not in managed,
        "covers_industry_universe": set(DEFAULT_UNIVERSE_SYMBOLS).issubset(managed),
        "top_n_respected": len(target_weights) <= 5,
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "status": status,
        "profile": CN_INDUSTRY_ETF_ROTATION_PROFILE,
        "as_of": SYNTHETIC_AS_OF,
        "target_weights": target_weights,
        "gross_exposure": gross_exposure,
        "cash_weight": max(0.0, 1.0 - gross_exposure),
        "risk_flags": list(decision.risk_flags),
        "diagnostics": {
            "signal_state": decision.diagnostics.get("signal_state"),
            "selected_symbols": list(decision.diagnostics.get("selected_symbols") or ()),
            "sentiment_mode": decision.diagnostics.get("sentiment_mode"),
            "target_annual_volatility": decision.diagnostics.get("target_annual_volatility"),
            "realized_portfolio_volatility": decision.diagnostics.get("realized_portfolio_volatility"),
            "signal_source": decision.diagnostics.get("signal_source"),
        },
        "checks": checks,
        "platform_requirements": requirements,
    }


def _print_text(report: dict[str, object]) -> None:
    print(f"status: {report['status']}")
    print(f"profile: {report['profile']}")
    print(f"as_of: {report['as_of']}")
    print(f"gross_exposure: {float(report['gross_exposure']):.2%}")
    print(f"cash_weight: {float(report['cash_weight']):.2%}")
    print("target_weights:")
    for symbol, weight in sorted(dict(report["target_weights"]).items(), key=lambda item: (-item[1], item[0])):
        print(f"  {symbol}: {float(weight):.2%}")
    print("checks:")
    for name, ok in dict(report["checks"]).items():
        print(f"  {'PASS' if ok else 'FAIL'} {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_smoke_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
