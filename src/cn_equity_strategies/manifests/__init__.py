from __future__ import annotations

from quant_platform_kit.strategy_contracts import StrategyManifest

from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy

CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE = index_etf_strategy.PROFILE_NAME


def _manifest(
    *,
    profile: str,
    display_name: str,
    description: str,
    aliases: tuple[str, ...] = (),
    required_inputs: frozenset[str] = frozenset(),
    default_config: dict[str, object] | None = None,
) -> StrategyManifest:
    return StrategyManifest(
        profile=profile,
        domain=index_etf_strategy.CN_EQUITY_DOMAIN,
        display_name=display_name,
        description=description,
        aliases=aliases,
        required_inputs=required_inputs,
        default_config=default_config or {},
    )


cn_index_etf_tactical_rotation_manifest = _manifest(
    profile=CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
    display_name="CN Index ETF Tactical Rotation",
    description=(
        "Monthly volatility-targeted rotation across A-share listed broad index, sector, "
        "and cross-market ETFs with CSI300 benchmark risk-off defensive switching."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
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
)

MANIFESTS = {
    cn_index_etf_tactical_rotation_manifest.profile: cn_index_etf_tactical_rotation_manifest,
}

MANIFEST_ALIASES = {
    str(alias).strip().lower(): manifest.profile
    for manifest in MANIFESTS.values()
    for alias in manifest.aliases
}


def get_strategy_manifest(profile: str) -> StrategyManifest:
    normalized = str(profile or "").strip().lower().replace("-", "_")
    return MANIFESTS[MANIFEST_ALIASES.get(normalized, normalized)]


__all__ = [
    "CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE",
    "MANIFESTS",
    "get_strategy_manifest",
    "cn_index_etf_tactical_rotation_manifest",
]
