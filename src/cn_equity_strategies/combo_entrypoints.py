"""CN equity combo entrypoints."""
from __future__ import annotations
from typing import Any
from quant_platform_kit.strategy_contracts import CallableStrategyEntrypoint, PositionTarget, StrategyContext, StrategyDecision
from cn_equity_strategies.combo_manifests import cn_equity_combo_manifest
from cn_equity_strategies.strategies import cn_equity_combo

def evaluate_cn_equity_combo(ctx: StrategyContext) -> StrategyDecision:
    config = {**cn_equity_combo_manifest.default_config, **(ctx.runtime_config or {})}
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    weights, signal_desc, has_cash, status_desc, metadata = cn_equity_combo.compute_signals(
        market_history=ctx.market_data.get("market_history"),
        current_holdings=set(),
        feature_snapshot=ctx.market_data.get("feature_snapshot"),
        **config,
    )
    diagnostics = {**metadata, "signal_description": signal_desc, "status_description": status_desc, "signal_source": cn_equity_combo.SIGNAL_SOURCE, "actionable": True}
    return StrategyDecision(
        positions=tuple(PositionTarget(symbol=str(s), target_weight=float(w), role="target") for s, w in sorted(weights.items()) if abs(float(w)) > 1e-12) if weights else (),
        risk_flags=("cash_residual",) if has_cash else (),
        diagnostics=diagnostics,
    )

cn_equity_combo_entrypoint = CallableStrategyEntrypoint(manifest=cn_equity_combo_manifest, _evaluate=evaluate_cn_equity_combo)
__all__ = ["evaluate_cn_equity_combo", "cn_equity_combo_entrypoint"]
