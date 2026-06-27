from __future__ import annotations

from quant_platform_kit.common.strategies import (
    StrategyCatalog,
    StrategyComponentDefinition,
    StrategyDefinition,
    StrategyEntrypointDefinition,
    StrategyMetadata,
    build_strategy_catalog,
    build_strategy_index_rows,
    get_catalog_compatible_platforms,
    get_catalog_strategy_definition,
    get_catalog_strategy_metadata,
    load_strategy_entrypoint,
    normalize_profile_name as qpk_normalize_profile_name,
)

from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy

CN_EQUITY_DOMAIN = index_etf_strategy.CN_EQUITY_DOMAIN
CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE = index_etf_strategy.PROFILE_NAME

CN_DIRECT_MARKET_HISTORY_PROFILES = frozenset({CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE})
CN_SNAPSHOT_BACKED_PROFILES = frozenset()
CN_EXTERNAL_SNAPSHOT_SCAFFOLD_PROFILES = frozenset({"cn_dividend_low_vol_quality_snapshot"})
CN_RESEARCH_BACKTEST_ONLY_PROFILES = frozenset()

STRATEGY_PLATFORM_COMPATIBILITY: dict[str, frozenset[str]] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: frozenset({"qmt"}),
}

STRATEGY_REQUIRED_INPUTS: dict[str, frozenset[str]] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: frozenset({"market_history"}),
}

STRATEGY_DEFAULT_CONFIG: dict[str, dict[str, object]] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: {
        "universe_symbols": index_etf_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": index_etf_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": index_etf_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "momentum_window_days": index_etf_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": index_etf_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": index_etf_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": index_etf_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": index_etf_strategy.DEFAULT_TOP_N,
        "min_momentum": index_etf_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": index_etf_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": index_etf_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": index_etf_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": index_etf_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": index_etf_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "execution_cash_reserve_ratio": index_etf_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
}

STRATEGY_ENTRYPOINT_ATTRIBUTES: dict[str, str] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: "cn_index_etf_tactical_rotation_entrypoint",
}

STRATEGY_TARGET_MODES: dict[str, str] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: "weight",
}


def _build_strategy_definition(
    profile: str,
    *,
    component_name: str,
    module_path: str,
) -> StrategyDefinition:
    return StrategyDefinition(
        profile=profile,
        domain=CN_EQUITY_DOMAIN,
        supported_platforms=STRATEGY_PLATFORM_COMPATIBILITY[profile],
        components=(
            StrategyComponentDefinition(
                name=component_name,
                module_path=module_path,
            ),
        ),
        entrypoint=StrategyEntrypointDefinition(
            module_path="cn_equity_strategies.entrypoints",
            attribute_name=STRATEGY_ENTRYPOINT_ATTRIBUTES[profile],
        ),
        required_inputs=STRATEGY_REQUIRED_INPUTS[profile],
        default_config=STRATEGY_DEFAULT_CONFIG[profile],
        target_mode=STRATEGY_TARGET_MODES[profile],
    )


STRATEGY_DEFINITIONS: dict[str, StrategyDefinition] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: _build_strategy_definition(
        CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        component_name="signal_logic",
        module_path="cn_equity_strategies.strategies.cn_index_etf_tactical_rotation",
    ),
}

STRATEGY_METADATA: dict[str, StrategyMetadata] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: StrategyMetadata(
        canonical_profile=CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        display_name="CN Index ETF Tactical Rotation",
        description=(
            "Runtime-enabled volatility-targeted rotation across A-share listed broad index, "
            "sector, and cross-market ETFs with CSI300 benchmark risk-off defensive switching."
        ),
        aliases=(),
        cadence="monthly review",
        asset_scope="cn_listed_index_etfs",
        benchmark="510300",
        role="cn_non_snapshot_index_etf_rotation",
        status="runtime_enabled",
    ),
}

PROFILE_ALIASES: dict[str, str] = {
    alias: metadata.canonical_profile
    for metadata in STRATEGY_METADATA.values()
    for alias in metadata.aliases
}

STRATEGY_CATALOG: StrategyCatalog = build_strategy_catalog(
    strategy_definitions=STRATEGY_DEFINITIONS,
    metadata=STRATEGY_METADATA,
    compatible_platforms=STRATEGY_PLATFORM_COMPATIBILITY,
    profile_aliases=PROFILE_ALIASES,
)


def normalize_profile_name(profile: str | None) -> str:
    return qpk_normalize_profile_name(profile).replace("-", "_")


def resolve_canonical_profile(profile: str | None) -> str:
    normalized = normalize_profile_name(profile)
    if not normalized:
        return normalized
    definition = get_catalog_strategy_definition(STRATEGY_CATALOG, normalized)
    return definition.profile


def get_strategy_definitions() -> dict[str, StrategyDefinition]:
    return dict(STRATEGY_DEFINITIONS)


def get_strategy_catalog() -> StrategyCatalog:
    return STRATEGY_CATALOG


def get_strategy_platform_compatibility_map() -> dict[str, frozenset[str]]:
    return dict(STRATEGY_PLATFORM_COMPATIBILITY)


def get_compatible_platforms(profile: str) -> frozenset[str]:
    return get_catalog_compatible_platforms(STRATEGY_CATALOG, profile)


def get_strategy_definition(profile: str) -> StrategyDefinition:
    return get_catalog_strategy_definition(STRATEGY_CATALOG, profile)


def get_strategy_entrypoint(profile: str):
    definition = get_strategy_definition(profile)
    metadata = get_strategy_metadata(profile)
    return load_strategy_entrypoint(definition, metadata=metadata)


def get_strategy_index_rows() -> list[dict[str, object]]:
    return build_strategy_index_rows(STRATEGY_CATALOG)


def get_strategy_metadata_map() -> dict[str, StrategyMetadata]:
    return dict(STRATEGY_METADATA)


def get_runtime_enabled_profiles() -> frozenset[str]:
    return frozenset(
        profile
        for profile, metadata in STRATEGY_METADATA.items()
        if str(metadata.status or "").strip().lower() == "runtime_enabled"
    )


def get_direct_market_history_profiles() -> frozenset[str]:
    return CN_DIRECT_MARKET_HISTORY_PROFILES


def get_snapshot_backed_profiles() -> frozenset[str]:
    return CN_SNAPSHOT_BACKED_PROFILES


def get_external_snapshot_scaffold_profiles() -> frozenset[str]:
    return CN_EXTERNAL_SNAPSHOT_SCAFFOLD_PROFILES


def get_research_backtest_only_profiles() -> frozenset[str]:
    return CN_RESEARCH_BACKTEST_ONLY_PROFILES


def get_strategy_metadata(profile: str) -> StrategyMetadata:
    return get_catalog_strategy_metadata(STRATEGY_CATALOG, profile)


def get_profile_aliases() -> dict[str, str]:
    return dict(PROFILE_ALIASES)
