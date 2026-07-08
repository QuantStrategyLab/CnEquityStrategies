from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from quant_platform_kit.risk.gate import apply_risk_gate as _qpk_apply_risk_gate
from quant_platform_kit.risk.gate import enrich_decision_risk_diagnostics
from quant_platform_kit.risk.portfolio_diagnostics import extract_portfolio_risk_diagnostics
from quant_platform_kit.strategy_contracts import PositionTarget, StrategyContext, StrategyDecision
from quant_platform_kit.strategy_lifecycle.performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 风控硬门 — 每个 entrypoint 返回 StrategyDecision 前必须调用
# ---------------------------------------------------------------------------

_performance_monitor: PerformanceMonitor | None = None


def record_strategy_decision(
    ctx: StrategyContext,
    decision: StrategyDecision,
    *,
    profile_id: str,
    domain: str,
) -> None:
    """Record per-run decision for live monitoring (roadmap 5a).

    entrypoints/evaluate only has `StrategyDecision`; execution_result is
    expected to be recorded by platform runtime later.
    """
    global _performance_monitor
    try:
        if _performance_monitor is None:
            _performance_monitor = PerformanceMonitor()
        _performance_monitor.record(
            profile_id,
            decision,
            execution_result={},
            domain=domain,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("PerformanceMonitor.record failed: %s", exc)


def apply_risk_gate(
    decision: StrategyDecision,
    *,
    ctx: StrategyContext | None = None,
    max_single_weight: float = 1.0,
    max_positions: int = 20,
    max_total_exposure: float = 1.0,
    portfolio_snapshot: Any | None = None,
    market_data: Mapping[str, Any] | None = None,
) -> StrategyDecision:
    """QPK unified risk gate: stop-loss, circuit breaker, concentration (task 8)."""
    snapshot = portfolio_snapshot if portfolio_snapshot is not None else (
        ctx.portfolio if ctx is not None else None
    )
    if snapshot is not None:
        portfolio_diag = extract_portfolio_risk_diagnostics(snapshot)
        decision = enrich_decision_risk_diagnostics(
            decision,
            unrealized_pnl_pct=portfolio_diag.get("unrealized_pnl_pct"),
            consecutive_losses=portfolio_diag.get("consecutive_losses"),
        )
    if market_data is None and ctx is not None:
        market_data = dict(ctx.market_data or {})
    return _qpk_apply_risk_gate(
        decision,
        max_single_weight=max_single_weight,
        max_positions=max_positions,
        max_total_exposure=max_total_exposure,
        portfolio_snapshot=snapshot,
        market_data=market_data,
    )


def merge_runtime_config(default_config: dict[str, object], ctx: StrategyContext) -> dict[str, object]:
    return {**dict(default_config or {}), **dict(ctx.runtime_config or {})}


def require_market_data(ctx: StrategyContext, key: str) -> Any:
    if key not in ctx.market_data:
        raise ValueError(f"StrategyContext.market_data[{key!r}] is required")
    return ctx.market_data[key]


def get_current_holdings(ctx: StrategyContext) -> set[str]:
    if "current_holdings" in ctx.state:
        raw = ctx.state["current_holdings"]
        return set(raw.keys() if isinstance(raw, dict) else raw)
    if ctx.portfolio is None:
        return set()
    return {
        str(getattr(position, "symbol", "") or "").strip().upper()
        for position in getattr(ctx.portfolio, "positions", ())
        if float(getattr(position, "quantity", 0.0) or 0.0) != 0.0
    }


def weights_to_positions(weights: dict[str, float] | None) -> tuple[PositionTarget, ...]:
    if not weights:
        return ()
    return tuple(
        PositionTarget(symbol=str(symbol), target_weight=float(weight), role="target")
        for symbol, weight in sorted(weights.items())
        if abs(float(weight)) > 1e-12
    )
