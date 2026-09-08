"""Bounded development search for the existing index ETF profile.

This is an optimize callback for QPK's research cycle, not a second lifecycle.
The caller supplies an approved, frozen development input. Close-only proxy
results remain learning evidence and cannot supply promotion/shadow evidence.
"""

from __future__ import annotations

from collections.abc import MutableSequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from quant_platform_kit.common.cn_equity_calendar import is_cn_equity_trading_day
from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
from quant_platform_kit.strategy_lifecycle.contracts import ParamDimension, ParamSearchSpace
from quant_platform_kit.strategy_lifecycle.param_optimizer import run_grid_search

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner
from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig

PROFILE = "cn_index_etf_tactical_rotation"
SYMBOLS = ("510300", "510500")
BASELINE_PARAMS = {"momentum_window_days": 60, "trend_window_days": 200, "top_n": 1}
SEARCH_SPACE = ParamSearchSpace(
    strategy_profile=PROFILE,
    domain="cn_equity",
    dimensions={
        "momentum_window_days": ParamDimension(
            name="momentum_window_days", param_type="int", bounds=(40, 80), step=20, current_value=60,
        ),
        "trend_window_days": ParamDimension(
            name="trend_window_days", param_type="int", bounds=(120, 200), step=80, current_value=200,
        ),
        "top_n": ParamDimension(name="top_n", param_type="int", bounds=(1, 2), step=1, current_value=1),
    },
)
FIXED_STRATEGY_PARAMS = {
    "universe_symbols": SYMBOLS,
    "defensive_symbols": (),
    "benchmark_symbol": "510300",
    "benchmark_trend_window_days": 200,
    "volatility_window_days": 63,
    "min_history_days": 220,
    "weighting_mode": "equal",
    "target_annual_volatility": None,
    "max_gross_exposure": 1.0,
    "max_pair_correlation": 1.0,
}
PROXY_LIMITATIONS = (
    "close_only_execution_proxy",
    "slippage_and_liquidity_not_validated",
    "corporate_actions_and_tradability_not_validated",
    "strict_purged_wfa_and_locked_oos_missing",
    "paired_forward_shadow_missing",
)


def make_index_etf_optimizer(
    *,
    market_history: pd.DataFrame | None,
    development_start: date,
    development_end: date,
    store: Any,
    trial_records: MutableSequence[dict[str, Any]],
):
    """Bind an explicit input/window to ``optimize(drift, budget)``.

    No provider, model, synthetic fallback, shadow, runtime or console call is
    made here. The owning job must persist ``trial_records`` even on failure.
    QPK persists successful BacktestResults in the supplied isolated store.
    """
    if market_history is None or market_history.empty:
        raise ValueError("market_history_required")
    if type(development_start) is not date or type(development_end) is not date:
        raise ValueError("development_window_required")
    if development_start >= development_end:
        raise ValueError("development_window_invalid")
    if not {"date", "symbol", "close"}.issubset(market_history.columns):
        raise ValueError("market_history_columns_missing")
    frame = market_history[["date", "symbol", "close"]].copy(deep=True)
    try:
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    except (TypeError, ValueError):
        raise ValueError("market_history_invalid") from None
    if frame["date"].dt.tz is not None or frame["date"].isna().any():
        raise ValueError("market_history_requires_local_session_dates")
    # Exclude holdout rows before inspecting prices or invoking the optimizer.
    frame = frame.loc[frame["date"] <= pd.Timestamp(development_end)].sort_values(["date", "symbol"])
    if frame.empty or frame["date"].max() < pd.Timestamp(development_start):
        raise ValueError("development_history_missing")
    # The currently pinned simulator calendar explicitly covers 2024–2026.
    # Outside that range it falls back to weekdays; do not call that complete.
    if frame["date"].min() < pd.Timestamp("2024-01-01") or development_end > date(2026, 12, 31):
        raise ValueError("development_calendar_out_of_coverage")
    if frame["close"].map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("market_history_price_invalid")
    try:
        frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    except (TypeError, ValueError):
        raise ValueError("market_history_price_invalid") from None
    if set(frame["symbol"]) != set(SYMBOLS):
        raise ValueError("market_history_requires_frozen_etf_universe")
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("market_history_duplicate")
    if frame["close"].isna().any() or not np.isfinite(frame["close"]).all() or not frame["close"].gt(0).all():
        raise ValueError("market_history_price_invalid")
    expected_days = pd.DatetimeIndex(
        day for day in pd.date_range(frame["date"].min(), development_end)
        if is_cn_equity_trading_day(day.date())
    )
    if any(
        set(frame.loc[frame["symbol"] == symbol, "date"]) != set(expected_days)
        for symbol in SYMBOLS
    ):
        raise ValueError("development_calendar_coverage_incomplete")
    warmup = frame.loc[frame["date"] < pd.Timestamp(development_start)]
    if any(len(warmup.loc[warmup["symbol"] == symbol]) < 220 for symbol in SYMBOLS):
        raise ValueError("development_warmup_incomplete")

    class RecordedRunner(CnProxyBacktestRunner):
        def run(self, strategy_profile, params, start_date=None, end_date=None):
            record = {
                "params": {**FIXED_STRATEGY_PARAMS, **dict(params)},
                "status": "failed", "reason": "backtest_failed",
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            }
            trial_records.append(record)
            try:
                result = super().run(strategy_profile, params, start_date, end_date)
            except Exception:
                raise RuntimeError("cn_research_backtest_failed") from None
            record.update(status="completed", reason=None)
            return result

    runner = RecordedRunner(
        market_history=frame,
        strategy_defaults=FIXED_STRATEGY_PARAMS,
        config=ProxyBacktestConfig(rebalance_frequency="monthly", min_history_days=220),
    )
    orchestrator = BacktestOrchestrator(store=store)
    orchestrator.register_runner("cn_equity", runner)

    def optimize(drift, budget):
        if drift.strategy_profile != PROFILE or drift.domain != "cn_equity":
            raise ValueError("research_candidate_identity_mismatch")
        if budget.max_param_keys < len(BASELINE_PARAMS) or budget.max_search_iterations < 1:
            raise ValueError("research_budget_insufficient")
        proposal = run_grid_search(
            PROFILE,
            domain="cn_equity",
            orchestrator=orchestrator,
            search_space=SEARCH_SPACE,
            current_params=BASELINE_PARAMS,
            start_date=development_start,
            end_date=development_end,
            max_combinations=min(12, budget.max_search_iterations),
        )
        store.save_proposal(proposal)
        return proposal

    return optimize
