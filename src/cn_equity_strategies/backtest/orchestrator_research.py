"""Shared helpers for research scripts to call BacktestOrchestrator adapters."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import pandas as pd

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner
from cn_equity_strategies.backtest.proxy_profile_registry import PROXY_PROFILE_REGISTRY


def _result_to_metrics(result: Any) -> dict[str, Any]:
    return {
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "annual_return": result.cagr,
        "total_return": result.total_return,
        "annual_volatility": result.volatility,
        "days": result.observation_count,
    }


def run_proxy_profile_backtest(
    profile: str,
    *,
    market_history: pd.DataFrame | None = None,
    synthetic_days: int = 900,
    start_date: date | None = None,
    end_date: date | None = None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a single-window proxy backtest through CnProxyBacktestRunner."""
    if profile not in PROXY_PROFILE_REGISTRY:
        raise ValueError(f"unsupported profile={profile!r}")

    spec = PROXY_PROFILE_REGISTRY[profile]
    runner = CnProxyBacktestRunner(market_history=market_history, synthetic_days=synthetic_days)
    merged_params = {"min_history_days": spec.default_min_history_days}
    if params:
        merged_params.update(dict(params))
    result = runner.run(profile, merged_params, start_date=start_date, end_date=end_date)
    return {
        "profile": profile,
        "params": merged_params,
        "start_date": result.start_date.isoformat() if result.start_date else None,
        "end_date": result.end_date.isoformat() if result.end_date else None,
        "metrics": _result_to_metrics(result),
        "source": "CnProxyBacktestRunner",
        "run_id": getattr(result, "run_id", None),
    }
