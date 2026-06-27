"""A-share equity strategy catalog and runtime adapters."""

__all__ = [
    "CN_EQUITY_DOMAIN",
    "CN_EXTERNAL_SNAPSHOT_SCAFFOLD_PROFILES",
    "CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE",
    "CN_DIRECT_MARKET_HISTORY_PROFILES",
    "CN_RESEARCH_BACKTEST_ONLY_PROFILES",
    "CN_SNAPSHOT_BACKED_PROFILES",
    "STRATEGY_CATALOG",
    "STRATEGY_DEFINITIONS",
    "get_compatible_platforms",
    "get_direct_market_history_profiles",
    "get_external_snapshot_scaffold_profiles",
    "get_platform_runtime_adapter",
    "get_profile_aliases",
    "get_qmt_optional_runtime_profiles",
    "get_qmt_rollout_allowlist",
    "get_research_backtest_only_profiles",
    "get_runtime_enabled_profiles",
    "get_snapshot_backed_profiles",
    "get_strategy_catalog",
    "get_strategy_definition",
    "get_strategy_definitions",
    "get_strategy_entrypoint",
    "get_strategy_index_rows",
    "get_strategy_metadata",
    "get_strategy_metadata_map",
    "get_strategy_platform_compatibility_map",
    "resolve_canonical_profile",
]


def __getattr__(name: str):
    if name in {
        "CN_EQUITY_DOMAIN",
        "CN_EXTERNAL_SNAPSHOT_SCAFFOLD_PROFILES",
        "CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE",
        "CN_DIRECT_MARKET_HISTORY_PROFILES",
        "CN_RESEARCH_BACKTEST_ONLY_PROFILES",
        "CN_SNAPSHOT_BACKED_PROFILES",
        "STRATEGY_CATALOG",
        "STRATEGY_DEFINITIONS",
        "get_compatible_platforms",
        "get_direct_market_history_profiles",
        "get_external_snapshot_scaffold_profiles",
        "get_profile_aliases",
        "get_qmt_optional_runtime_profiles",
        "get_qmt_rollout_allowlist",
        "get_research_backtest_only_profiles",
        "get_runtime_enabled_profiles",
        "get_snapshot_backed_profiles",
        "get_strategy_catalog",
        "get_strategy_definition",
        "get_strategy_definitions",
        "get_strategy_entrypoint",
        "get_strategy_index_rows",
        "get_strategy_metadata",
        "get_strategy_metadata_map",
        "get_strategy_platform_compatibility_map",
        "resolve_canonical_profile",
    }:
        from . import catalog as _catalog

        return getattr(_catalog, name)
    if name == "get_platform_runtime_adapter":
        from .runtime_adapters import get_platform_runtime_adapter as _get_platform_runtime_adapter

        return _get_platform_runtime_adapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
