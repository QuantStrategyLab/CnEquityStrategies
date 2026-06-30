from __future__ import annotations

from quant_platform_kit.strategy_contracts import CallableStrategyEntrypoint, StrategyContext, StrategyDecision

from cn_equity_strategies.manifests import (
    cn_dividend_quality_snapshot_manifest,
    cn_index_etf_tactical_rotation_manifest,
    cn_industry_etf_rotation_aggressive_manifest,
    cn_industry_etf_rotation_manifest,
)
from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_quality_strategy
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_etf_aggressive_strategy

from ._common import get_current_holdings, merge_runtime_config, require_market_data, weights_to_positions


def evaluate_cn_industry_etf_rotation(ctx: StrategyContext) -> StrategyDecision:
    config = merge_runtime_config(cn_industry_etf_rotation_manifest.default_config, ctx)
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    config.pop("run_as_of", None)
    weights, signal_desc, has_cash_residual, status_desc, metadata = industry_etf_strategy.compute_signals(
        require_market_data(ctx, "market_history"),
        get_current_holdings(ctx),
        **config,
    )
    diagnostics = {
        **metadata,
        "signal_description": signal_desc,
        "status_description": status_desc,
        "signal_source": industry_etf_strategy.SIGNAL_SOURCE,
        "actionable": True,
    }
    risk_flags: tuple[str, ...] = ()
    if has_cash_residual:
        risk_flags += ("cash_residual",)
    return StrategyDecision(
        positions=weights_to_positions(weights),
        risk_flags=risk_flags,
        diagnostics=diagnostics,
    )


cn_industry_etf_rotation_entrypoint = CallableStrategyEntrypoint(
    manifest=cn_industry_etf_rotation_manifest,
    _evaluate=evaluate_cn_industry_etf_rotation,
)


def evaluate_cn_industry_etf_rotation_aggressive(ctx: StrategyContext) -> StrategyDecision:
    config = merge_runtime_config(cn_industry_etf_rotation_aggressive_manifest.default_config, ctx)
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    config.pop("run_as_of", None)
    weights, signal_desc, has_cash_residual, status_desc, metadata = industry_etf_aggressive_strategy.compute_signals(
        require_market_data(ctx, "market_history"),
        get_current_holdings(ctx),
        **config,
    )
    diagnostics = {
        **metadata,
        "signal_description": signal_desc,
        "status_description": status_desc,
        "signal_source": industry_etf_aggressive_strategy.SIGNAL_SOURCE,
        "actionable": True,
    }
    risk_flags: tuple[str, ...] = ()
    if has_cash_residual:
        risk_flags += ("cash_residual",)
    return StrategyDecision(
        positions=weights_to_positions(weights),
        risk_flags=risk_flags,
        diagnostics=diagnostics,
    )


cn_industry_etf_rotation_aggressive_entrypoint = CallableStrategyEntrypoint(
    manifest=cn_industry_etf_rotation_aggressive_manifest,
    _evaluate=evaluate_cn_industry_etf_rotation_aggressive,
)


def evaluate_cn_index_etf_tactical_rotation(ctx: StrategyContext) -> StrategyDecision:
    config = merge_runtime_config(cn_index_etf_tactical_rotation_manifest.default_config, ctx)
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    config.pop("run_as_of", None)
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


def evaluate_cn_dividend_quality_snapshot(ctx: StrategyContext) -> StrategyDecision:
    config = merge_runtime_config(cn_dividend_quality_snapshot_manifest.default_config, ctx)
    config.pop("execution_cash_reserve_ratio", None)
    config.pop("rebalance_frequency", None)
    config.pop("run_as_of", None)
    weights, signal_desc, has_cash_residual, status_desc, metadata = dividend_quality_strategy.compute_signals(
        require_market_data(ctx, "feature_snapshot"),
        get_current_holdings(ctx),
        **config,
    )
    diagnostics = {
        **metadata,
        "signal_description": signal_desc,
        "status_description": status_desc,
        "signal_source": dividend_quality_strategy.SIGNAL_SOURCE,
        "actionable": True,
    }
    risk_flags: tuple[str, ...] = ()
    if has_cash_residual:
        risk_flags += ("cash_residual",)
    return StrategyDecision(
        positions=weights_to_positions(weights),
        risk_flags=risk_flags,
        diagnostics=diagnostics,
    )


cn_dividend_quality_snapshot_entrypoint = CallableStrategyEntrypoint(
    manifest=cn_dividend_quality_snapshot_manifest,
    _evaluate=evaluate_cn_dividend_quality_snapshot,
)


# ---------------------------------------------------------------------------
# CN Equity Combo entrypoint
# ---------------------------------------------------------------------------


def evaluate_cn_equity_combo(ctx: StrategyContext) -> StrategyDecision:
    from cn_equity_strategies.combo_entrypoints import evaluate_cn_equity_combo as _eval
    return _eval(ctx)


from cn_equity_strategies.combo_manifests import cn_equity_combo_manifest  # noqa: E402

cn_equity_combo_entrypoint = CallableStrategyEntrypoint(
    manifest=cn_equity_combo_manifest,
    _evaluate=evaluate_cn_equity_combo,
)


__all__ = [
    "evaluate_cn_dividend_quality_snapshot",
    "evaluate_cn_index_etf_tactical_rotation",
    "evaluate_cn_industry_etf_rotation",
    "evaluate_cn_industry_etf_rotation_aggressive",
    "evaluate_cn_equity_combo",
    "cn_dividend_quality_snapshot_entrypoint",
    "cn_index_etf_tactical_rotation_entrypoint",
    "cn_industry_etf_rotation_aggressive_entrypoint",
    "cn_industry_etf_rotation_entrypoint",
    "cn_equity_combo_entrypoint",
]
