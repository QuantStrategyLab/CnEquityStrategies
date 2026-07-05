from __future__ import annotations

from quant_platform_kit.strategy_contracts import StrategyManifest

from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_quality_strategy
from cn_equity_strategies.strategies import (
    cn_chinext_growth_momentum_quality as chinext_growth_momentum_quality_strategy,
    cn_chinext_growth_momentum_quality_snapshot as chinext_growth_momentum_quality_snapshot_strategy,
)
from cn_equity_strategies.strategies import cn_chinext_tactical_rotation as chinext_tactical_strategy
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_etf_aggressive_strategy
from cn_equity_strategies.strategies import cn_star_growth_momentum_quality as star_growth_momentum_quality_strategy

CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE = index_etf_strategy.PROFILE_NAME
CN_CHINEXT_TACTICAL_ROTATION_PROFILE = chinext_tactical_strategy.PROFILE_NAME
CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_PROFILE = (
    chinext_growth_momentum_quality_strategy.PROFILE_NAME
)
CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_SNAPSHOT_PROFILE = (
    chinext_growth_momentum_quality_snapshot_strategy.PROFILE_NAME
)
CN_STAR_GROWTH_MOMENTUM_QUALITY_PROFILE = star_growth_momentum_quality_strategy.PROFILE_NAME
CN_INDUSTRY_ETF_ROTATION_PROFILE = industry_etf_strategy.PROFILE_NAME
CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE = industry_etf_aggressive_strategy.PROFILE_NAME
CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE = dividend_quality_strategy.PROFILE_NAME


def _manifest(
    *,
    profile: str,
    domain: str,
    display_name: str,
    description: str,
    aliases: tuple[str, ...] = (),
    required_inputs: frozenset[str] = frozenset(),
    default_config: dict[str, object] | None = None,
) -> StrategyManifest:
    return StrategyManifest(
        profile=profile,
        domain=domain,
        display_name=display_name,
        description=description,
        aliases=aliases,
        required_inputs=required_inputs,
        default_config=default_config or {},
    )


cn_industry_etf_rotation_manifest = _manifest(
    profile=CN_INDUSTRY_ETF_ROTATION_PROFILE,
    domain=industry_etf_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Industry ETF Rotation",
    description=(
        "Conservative v1 (runtime default): monthly pure-momentum rotation across 14 A-share "
        "industry/style ETFs — top5, vol target 20%, sentiment off, benchmark risk-off off."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "universe_symbols": industry_etf_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": industry_etf_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": industry_etf_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "enable_benchmark_risk_off": industry_etf_strategy.DEFAULT_ENABLE_BENCHMARK_RISK_OFF,
        "momentum_window_days": industry_etf_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": industry_etf_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": industry_etf_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": industry_etf_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": industry_etf_strategy.DEFAULT_TOP_N,
        "min_momentum": industry_etf_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": industry_etf_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": industry_etf_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": industry_etf_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": industry_etf_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": industry_etf_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": industry_etf_strategy.DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": industry_etf_strategy.DEFAULT_SENTIMENT_MODE,
        "execution_cash_reserve_ratio": industry_etf_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
)

cn_industry_etf_rotation_aggressive_manifest = _manifest(
    profile=CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    domain=industry_etf_aggressive_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Industry ETF Rotation Aggressive",
    description=(
        "Research-only aggressive v1: full 14-ETF pool, vol target 25%, pure momentum; "
        "not a runtime default."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "universe_symbols": industry_etf_aggressive_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": industry_etf_aggressive_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": industry_etf_aggressive_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "enable_benchmark_risk_off": industry_etf_aggressive_strategy.DEFAULT_ENABLE_BENCHMARK_RISK_OFF,
        "momentum_window_days": industry_etf_aggressive_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": industry_etf_aggressive_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": industry_etf_aggressive_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": industry_etf_aggressive_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": industry_etf_aggressive_strategy.DEFAULT_TOP_N,
        "min_momentum": industry_etf_aggressive_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": industry_etf_aggressive_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": industry_etf_aggressive_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": industry_etf_aggressive_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": industry_etf_aggressive_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": industry_etf_aggressive_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": industry_etf_aggressive_strategy.DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": industry_etf_aggressive_strategy.DEFAULT_SENTIMENT_MODE,
        "execution_cash_reserve_ratio": industry_etf_aggressive_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
)

cn_index_etf_tactical_rotation_manifest = _manifest(
    profile=CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
    domain=index_etf_strategy.CN_EQUITY_DOMAIN,
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

cn_chinext_tactical_rotation_manifest = _manifest(
    profile=CN_CHINEXT_TACTICAL_ROTATION_PROFILE,
    domain=chinext_tactical_strategy.CN_EQUITY_DOMAIN,
    display_name="CN ChiNext Tactical Rotation",
    description=(
        "Research-only ChiNext tactical rotation using a focused two-ETF sleeve with CSI300 "
        "benchmark risk-off switching."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "universe_symbols": chinext_tactical_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": chinext_tactical_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": chinext_tactical_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "momentum_window_days": chinext_tactical_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": chinext_tactical_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": chinext_tactical_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": chinext_tactical_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": chinext_tactical_strategy.DEFAULT_TOP_N,
        "min_momentum": chinext_tactical_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": chinext_tactical_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": chinext_tactical_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": chinext_tactical_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": chinext_tactical_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": chinext_tactical_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": chinext_tactical_strategy.DEFAULT_MAX_PAIR_CORRELATION,
    },
)

cn_chinext_growth_momentum_quality_manifest = _manifest(
    profile=CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_PROFILE,
    domain=chinext_growth_momentum_quality_strategy.CN_EQUITY_DOMAIN,
    display_name="CN ChiNext Growth Momentum Quality",
    description=(
        "Research-only ChiNext growth sleeve using momentum, trend, and benchmark risk-off switching."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "universe_symbols": chinext_growth_momentum_quality_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": chinext_growth_momentum_quality_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": chinext_growth_momentum_quality_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "momentum_window_days": chinext_growth_momentum_quality_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": chinext_growth_momentum_quality_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": chinext_growth_momentum_quality_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": chinext_growth_momentum_quality_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": chinext_growth_momentum_quality_strategy.DEFAULT_TOP_N,
        "min_momentum": chinext_growth_momentum_quality_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": chinext_growth_momentum_quality_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": chinext_growth_momentum_quality_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": chinext_growth_momentum_quality_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": chinext_growth_momentum_quality_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": chinext_growth_momentum_quality_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": chinext_growth_momentum_quality_strategy.DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": chinext_growth_momentum_quality_strategy.DEFAULT_SENTIMENT_MODE,
        "execution_cash_reserve_ratio": chinext_growth_momentum_quality_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
)

cn_chinext_growth_momentum_quality_snapshot_manifest = _manifest(
    profile=CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_SNAPSHOT_PROFILE,
    domain=chinext_growth_momentum_quality_strategy.CN_EQUITY_DOMAIN,
    display_name="CN ChiNext Growth Momentum Quality Snapshot",
    description=(
        "Research-only snapshot-backed ChiNext selector emphasizing growth, momentum, "
        "quality, and liquidity with defensive exposure control."
    ),
    aliases=(),
    required_inputs=frozenset({"feature_snapshot"}),
    default_config={
        "safe_haven": chinext_growth_momentum_quality_snapshot_strategy.SAFE_HAVEN,
        "holdings_count": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_HOLDINGS_COUNT,
        "single_name_cap": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_SINGLE_NAME_CAP,
        "sector_cap": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_SECTOR_CAP,
        "min_adv20_cny": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_ADV20_CNY,
        "min_market_cap_cny": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_MARKET_CAP_CNY,
        "min_revenue_yoy": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_REVENUE_YOY,
        "min_profit_yoy": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_PROFIT_YOY,
        "min_momentum": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_MOMENTUM,
        "min_list_days": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_MIN_LIST_DAYS,
        "hold_buffer": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_HOLD_BUFFER,
        "hold_bonus": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_HOLD_BONUS,
        "risk_on_exposure": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_RISK_ON_EXPOSURE,
        "soft_defense_exposure": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_SOFT_DEFENSE_EXPOSURE,
        "hard_defense_exposure": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_HARD_DEFENSE_EXPOSURE,
        "soft_breadth_threshold": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_SOFT_BREADTH_THRESHOLD,
        "hard_breadth_threshold": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_HARD_BREADTH_THRESHOLD,
        "execution_cash_reserve_ratio": chinext_growth_momentum_quality_snapshot_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
        "rebalance_frequency": "monthly",
    },
)

cn_star_growth_momentum_quality_manifest = _manifest(
    profile=CN_STAR_GROWTH_MOMENTUM_QUALITY_PROFILE,
    domain=star_growth_momentum_quality_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Star Growth Momentum Quality",
    description=(
        "Research-only STAR sleeve using momentum, trend, and benchmark risk-off switching."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "universe_symbols": star_growth_momentum_quality_strategy.DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": star_growth_momentum_quality_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": star_growth_momentum_quality_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "momentum_window_days": star_growth_momentum_quality_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": star_growth_momentum_quality_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": star_growth_momentum_quality_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": star_growth_momentum_quality_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": star_growth_momentum_quality_strategy.DEFAULT_TOP_N,
        "min_momentum": star_growth_momentum_quality_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": star_growth_momentum_quality_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": star_growth_momentum_quality_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": star_growth_momentum_quality_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": star_growth_momentum_quality_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": star_growth_momentum_quality_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": star_growth_momentum_quality_strategy.DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": star_growth_momentum_quality_strategy.DEFAULT_SENTIMENT_MODE,
        "execution_cash_reserve_ratio": star_growth_momentum_quality_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
)

cn_dividend_quality_snapshot_manifest = _manifest(
    profile=CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
    domain=dividend_quality_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Dividend Quality Snapshot",
    description=(
        "Snapshot-backed monthly A-share selector emphasizing dividend yield and quality "
        "factors with breadth-based defensive exposure control."
    ),
    aliases=(),
    required_inputs=frozenset({"feature_snapshot"}),
    default_config={
        "safe_haven": dividend_quality_strategy.SAFE_HAVEN,
        "holdings_count": dividend_quality_strategy.DEFAULT_HOLDINGS_COUNT,
        "single_name_cap": dividend_quality_strategy.DEFAULT_SINGLE_NAME_CAP,
        "sector_cap": dividend_quality_strategy.DEFAULT_SECTOR_CAP,
        "min_adv20_cny": dividend_quality_strategy.DEFAULT_MIN_ADV20_CNY,
        "min_market_cap_cny": dividend_quality_strategy.DEFAULT_MIN_MARKET_CAP_CNY,
        "min_dividend_yield": dividend_quality_strategy.DEFAULT_MIN_DIVIDEND_YIELD,
        "max_dividend_yield": dividend_quality_strategy.DEFAULT_MAX_DIVIDEND_YIELD,
        "min_dividend_stability": dividend_quality_strategy.DEFAULT_MIN_DIVIDEND_STABILITY,
        "min_roe_ttm": dividend_quality_strategy.DEFAULT_MIN_ROE_TTM,
        "max_payout_ratio": dividend_quality_strategy.DEFAULT_MAX_PAYOUT_RATIO,
        "max_suspension_days_63": dividend_quality_strategy.DEFAULT_MAX_SUSPENSION_DAYS_63,
        "min_list_days": dividend_quality_strategy.DEFAULT_MIN_LIST_DAYS,
        "hold_buffer": dividend_quality_strategy.DEFAULT_HOLD_BUFFER,
        "hold_bonus": dividend_quality_strategy.DEFAULT_HOLD_BONUS,
        "risk_on_exposure": dividend_quality_strategy.DEFAULT_RISK_ON_EXPOSURE,
        "soft_defense_exposure": dividend_quality_strategy.DEFAULT_SOFT_DEFENSE_EXPOSURE,
        "hard_defense_exposure": dividend_quality_strategy.DEFAULT_HARD_DEFENSE_EXPOSURE,
        "soft_breadth_threshold": dividend_quality_strategy.DEFAULT_SOFT_BREADTH_THRESHOLD,
        "hard_breadth_threshold": dividend_quality_strategy.DEFAULT_HARD_BREADTH_THRESHOLD,
        "execution_cash_reserve_ratio": dividend_quality_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
        "rebalance_frequency": "monthly",
    },
)

MANIFESTS = {
    cn_industry_etf_rotation_manifest.profile: cn_industry_etf_rotation_manifest,
    cn_industry_etf_rotation_aggressive_manifest.profile: cn_industry_etf_rotation_aggressive_manifest,
    cn_index_etf_tactical_rotation_manifest.profile: cn_index_etf_tactical_rotation_manifest,
    cn_chinext_tactical_rotation_manifest.profile: cn_chinext_tactical_rotation_manifest,
    cn_chinext_growth_momentum_quality_manifest.profile: cn_chinext_growth_momentum_quality_manifest,
    cn_dividend_quality_snapshot_manifest.profile: cn_dividend_quality_snapshot_manifest,
    cn_star_growth_momentum_quality_manifest.profile: cn_star_growth_momentum_quality_manifest,
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
    "CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE",
    "CN_CHINEXT_TACTICAL_ROTATION_PROFILE",
    "CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_PROFILE",
    "CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_SNAPSHOT_PROFILE",
    "CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE",
    "CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE",
    "CN_INDUSTRY_ETF_ROTATION_PROFILE",
    "CN_STAR_GROWTH_MOMENTUM_QUALITY_PROFILE",
    "MANIFESTS",
    "get_strategy_manifest",
    "cn_chinext_growth_momentum_quality_manifest",
    "cn_chinext_growth_momentum_quality_snapshot_manifest",
    "cn_chinext_tactical_rotation_manifest",
    "cn_dividend_quality_snapshot_manifest",
    "cn_index_etf_tactical_rotation_manifest",
    "cn_industry_etf_rotation_aggressive_manifest",
    "cn_industry_etf_rotation_manifest",
    "cn_star_growth_momentum_quality_manifest",
]
