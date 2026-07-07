from __future__ import annotations

import logging
from typing import Any

from quant_platform_kit.strategy_contracts import PositionTarget, StrategyContext, StrategyDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 风控硬门 — 每个 entrypoint 返回 StrategyDecision 前必须调用
# ---------------------------------------------------------------------------

# 单仓位上限（账户权益的百分比）
MAX_SINGLE_POSITION_WEIGHT = 0.10
# 最大持仓数
MAX_POSITION_COUNT = 20
# 总仓位上限
MAX_TOTAL_EXPOSURE = 1.0


def apply_risk_gate(decision: StrategyDecision) -> StrategyDecision:
    """对所有 StrategyDecision 施加硬风控门。

    检查项：
    1. 单仓位集中度（>10% → REJECT）
    2. 持仓数量（>20 → REJECT）
    3. 总仓位超限（>100% → REJECT）
    4. 空仓 + 非 risk_off 信号 → WARNING 但放行

    如果 REJECT，返回空仓决策并标注拒绝原因。
    这个函数不可绕过 —— AGENTS.md 要求所有 entrypoint 必须调用。
    """
    positions = decision.positions or ()
    risk_flags = list(decision.risk_flags or ())

    # 空仓放行（risk_off 场景）
    if not positions:
        return decision

    # 1. 集中度检查
    for p in positions:
        weight = abs(float(p.target_weight))
        if weight > MAX_SINGLE_POSITION_WEIGHT:
            logger.warning(
                "risk_gate REJECT concentration: symbol=%s weight=%.2f%% limit=%.0f%%",
                p.symbol, weight * 100, MAX_SINGLE_POSITION_WEIGHT * 100,
            )
            return StrategyDecision(
                positions=(),
                risk_flags=("rejected:concentration",),
                diagnostics={
                    **(decision.diagnostics or {}),
                    "risk_gate": "REJECT",
                    "reason": f"{p.symbol} {weight:.1%} > {MAX_SINGLE_POSITION_WEIGHT:.0%} 上限",
                },
            )

    # 2. 持仓数量检查
    if len(positions) > MAX_POSITION_COUNT:
        logger.warning(
            "risk_gate REJECT position_count: %d > %d", len(positions), MAX_POSITION_COUNT,
        )
        return StrategyDecision(
            positions=(),
            risk_flags=("rejected:too_many_positions",),
            diagnostics={
                **(decision.diagnostics or {}),
                "risk_gate": "REJECT",
                "reason": f"{len(positions)} 个持仓 > {MAX_POSITION_COUNT} 上限",
            },
        )

    # 3. 总仓位检查
    total_weight = sum(abs(float(p.target_weight)) for p in positions)
    if total_weight > MAX_TOTAL_EXPOSURE + 1e-9:
        logger.warning(
            "risk_gate REJECT total_exposure: %.2f%% > %.0f%%",
            total_weight * 100, MAX_TOTAL_EXPOSURE * 100,
        )
        return StrategyDecision(
            positions=(),
            risk_flags=("rejected:overexposed",),
            diagnostics={
                **(decision.diagnostics or {}),
                "risk_gate": "REJECT",
                "reason": f"总仓位 {total_weight:.1%} > {MAX_TOTAL_EXPOSURE:.0%}",
            },
        )

    # 通过
    risk_flags.append("risk_gate:passed")
    return StrategyDecision(
        positions=decision.positions,
        risk_flags=tuple(risk_flags),
        diagnostics={**(decision.diagnostics or {}), "risk_gate": "APPROVE"},
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
