from __future__ import annotations

from quant_platform_kit.strategy_contracts import CallableStrategyEntrypoint, StrategyContext, StrategyDecision

from cn_equity_strategies.manifests import cn_index_etf_tactical_rotation_manifest
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy

from ._common import get_current_holdings, merge_runtime_config, require_market_data, weights_to_positions


def evaluate_cn_index_etf_tactical_rotation(ctx: StrategyContext) -> StrategyDecision:
    config = merge_runtime_config(cn_index_etf_tactical_rotation_manifest.default_config, ctx)
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    weights, signal_desc, has_cash_residual, status_desc, metadata = index_etf_strategy.compute_signals(
        require_market_data(ctx, "market_history"),
        get_current_holdings(ctx),
        **config,
    )
    diagnostics = {
        **metadata,
        "signal_description": signal_desc,
        "status_description": status_desc,
        "signal_source": index_etf_strategy.SIGNAL_SOURCE,
        "actionable": True,
    }
    risk_flags: tuple[str, ...] = ()
    if has_cash_residual:
        risk_flags += ("cash_residual",)
    if metadata.get("benchmark_risk_off"):
        risk_flags += ("benchmark_risk_off",)
    return StrategyDecision(
        positions=weights_to_positions(weights),
        risk_flags=risk_flags,
        diagnostics=diagnostics,
    )


cn_index_etf_tactical_rotation_entrypoint = CallableStrategyEntrypoint(
    manifest=cn_index_etf_tactical_rotation_manifest,
    _evaluate=evaluate_cn_index_etf_tactical_rotation,
)


__all__ = [
    "evaluate_cn_index_etf_tactical_rotation",
    "cn_index_etf_tactical_rotation_entrypoint",
]
