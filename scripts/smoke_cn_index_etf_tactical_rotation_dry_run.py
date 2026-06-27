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
from cn_equity_strategies.catalog import CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE  # noqa: E402
from cn_equity_strategies.runtime_adapters import describe_platform_runtime_requirements  # noqa: E402
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (  # noqa: E402
    NEW_ENERGY_ETF_SYMBOL,
    SEMICONDUCTOR_ETF_SYMBOL,
    extract_managed_symbols,
)

SYNTHETIC_AS_OF = "2026-02-25"


def build_synthetic_market_history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=320)
    rates = {
        "510300": 1.0002,
        "510500": 1.0001,
        "159915": 0.9998,
        "588000": 1.0000,
        "512100": 1.0003,
        "512170": 1.0004,
        "515030": 1.0009,
        "512760": 1.0008,
        "518880": 1.0005,
        "513100": 1.0007,
        "511880": 1.00001,
        "511260": 1.00002,
    }
    rows: list[dict[str, object]] = []
    for symbol in extract_managed_symbols():
        price = 20.0
        for idx, date in enumerate(dates):
            price *= rates[symbol]
            close = price * (1.0 + 0.04 * ((idx % 5) - 2) / 5)
            rows.append({"date": date, "symbol": symbol, "close": close})
    return pd.DataFrame(rows)


def build_smoke_report() -> dict[str, object]:
    entrypoint = get_strategy_entrypoint(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE)
    decision = entrypoint.evaluate(
        StrategyContext(
            as_of=SYNTHETIC_AS_OF,
            market_data={"market_history": build_synthetic_market_history()},
            runtime_config={"min_history_days": 220},
        )
    )
    target_weights = {
        position.symbol: float(position.target_weight or 0.0)
        for position in decision.positions
        if float(position.target_weight or 0.0) > 1e-12
    }
    gross_exposure = sum(target_weights.values())
    requirements = describe_platform_runtime_requirements(
        CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        platform_id="qmt",
    )
    checks = {
        "strategy_actionable": bool(decision.diagnostics.get("actionable")),
        "uses_direct_market_history": decision.diagnostics.get("signal_source") == "daily_market_history",
        "weights_non_empty": bool(target_weights),
        "gross_exposure_lte_one": 0.0 < gross_exposure <= 1.0,
        "qmt_direct_inputs": requirements["input_mode"] == "market_history",
        "expected_leaders_selected": set(target_weights) == {NEW_ENERGY_ETF_SYMBOL, SEMICONDUCTOR_ETF_SYMBOL},
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "status": status,
        "profile": CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        "as_of": SYNTHETIC_AS_OF,
        "target_weights": target_weights,
        "gross_exposure": gross_exposure,
        "cash_weight": max(0.0, 1.0 - gross_exposure),
        "risk_flags": list(decision.risk_flags),
        "diagnostics": {
            "signal_state": decision.diagnostics.get("signal_state"),
            "selected_symbols": list(decision.diagnostics.get("selected_symbols") or ()),
            "target_annual_volatility": decision.diagnostics.get("target_annual_volatility"),
            "realized_portfolio_volatility": decision.diagnostics.get("realized_portfolio_volatility"),
            "signal_source": decision.diagnostics.get("signal_source"),
            "benchmark_risk_off": decision.diagnostics.get("benchmark_risk_off"),
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
