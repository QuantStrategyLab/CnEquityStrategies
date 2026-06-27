from __future__ import annotations

from typing import Any

from quant_platform_kit.strategy_contracts import PositionTarget, StrategyContext


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
