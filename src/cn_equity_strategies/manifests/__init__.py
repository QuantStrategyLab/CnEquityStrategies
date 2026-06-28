from __future__ import annotations

from quant_platform_kit.strategy_contracts import StrategyManifest

from cn_equity_strategies.strategies import cn_csi500_multi_factor_snapshot as csi500_multi_factor_strategy
from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_quality_strategy
from cn_equity_strategies.strategies import cn_equity_combo as combo_strategy
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation as industry_etf_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as industry_etf_aggressive_strategy
from cn_equity_strategies.strategies import cn_stock_momentum_rotation as stock_momentum_strategy

CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE = index_etf_strategy.PROFILE_NAME
CN_INDUSTRY_ETF_ROTATION_PROFILE = industry_etf_strategy.PROFILE_NAME
CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE = industry_etf_aggressive_strategy.PROFILE_NAME
CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE = dividend_quality_strategy.PROFILE_NAME
CN_STOCK_MOMENTUM_ROTATION_PROFILE = stock_momentum_strategy.PROFILE_NAME
CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE = csi500_multi_factor_strategy.PROFILE_NAME
CN_EQUITY_COMBO_PROFILE = combo_strategy.PROFILE_NAME


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
    display_name="CN Industry ETF Rotation (Conservative)",
    description=(
        "Conservative v1 (research only): monthly pure-momentum rotation across 14 A-share "
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
    display_name="CN Industry ETF Rotation",
    description=(
        "Default ETF rotation: monthly pure-momentum rotation across 14 A-share "
        "industry/style ETFs — top5, vol target 25%, sentiment off, benchmark risk-off off."
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

cn_stock_momentum_rotation_manifest = _manifest(
    profile=CN_STOCK_MOMENTUM_ROTATION_PROFILE,
    domain=stock_momentum_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Stock Momentum Rotation",
    description=(
        "vol25 MA120 CSI500 stock momentum rotation with CSI300 benchmark risk-off; "
        "universe resolved at runtime from CSI500 constituents via akshare."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history"}),
    default_config={
        "defensive_symbols": stock_momentum_strategy.DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": stock_momentum_strategy.DEFAULT_BENCHMARK_SYMBOL,
        "enable_benchmark_risk_off": stock_momentum_strategy.DEFAULT_ENABLE_BENCHMARK_RISK_OFF,
        "momentum_window_days": stock_momentum_strategy.DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": stock_momentum_strategy.DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": stock_momentum_strategy.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": stock_momentum_strategy.DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": stock_momentum_strategy.DEFAULT_TOP_N,
        "min_momentum": stock_momentum_strategy.DEFAULT_MIN_MOMENTUM,
        "rebalance_frequency": stock_momentum_strategy.DEFAULT_REBALANCE_FREQUENCY,
        "weighting_mode": stock_momentum_strategy.DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": stock_momentum_strategy.DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": stock_momentum_strategy.DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": stock_momentum_strategy.DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": stock_momentum_strategy.DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": stock_momentum_strategy.DEFAULT_SENTIMENT_MODE,
        "execution_cash_reserve_ratio": stock_momentum_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
    },
)

cn_equity_combo_manifest = _manifest(
    profile=CN_EQUITY_COMBO_PROFILE,
    domain=combo_strategy.CN_EQUITY_DOMAIN,
    display_name="CN Equity Combo",
    description=(
        "Combined A-share strategy: ETF rotation (40%) + CSI500 stock momentum "
        "(40%) + dividend quality (20%) with dynamic regime-based weight adjustment."
    ),
    aliases=(),
    required_inputs=frozenset({"market_history", "feature_snapshot"}),
    default_config={
        "etf_weight": combo_strategy.DEFAULT_ETF_WEIGHT,
        "stock_weight": combo_strategy.DEFAULT_STOCK_WEIGHT,
        "dividend_weight": combo_strategy.DEFAULT_DIVIDEND_WEIGHT,
        "dynamic_mode": True,
        "execution_cash_reserve_ratio": 0.02,
        "rebalance_frequency": "monthly",
    },
)

cn_csi500_multi_factor_snapshot_manifest = _manifest(
    profile=CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE,
    domain=csi500_multi_factor_strategy.CN_EQUITY_DOMAIN,
    display_name="CN CSI500 Multi-Factor Snapshot",
    description=(
        "Snapshot-backed CSI500 multi-factor stock selector combining momentum, "
        "relative momentum, trend, quality, and low-vol factors with breadth-based "
        "defensive exposure control."
    ),
    aliases=(),
    required_inputs=frozenset({"feature_snapshot"}),
    default_config={
        "holdings_count": csi500_multi_factor_strategy.DEFAULT_HOLDINGS_COUNT,
        "single_name_cap": csi500_multi_factor_strategy.DEFAULT_SINGLE_NAME_CAP,
        "sector_cap": csi500_multi_factor_strategy.DEFAULT_SECTOR_CAP,
        "min_adv20_cny": csi500_multi_factor_strategy.DEFAULT_MIN_ADV20_CNY,
        "min_market_cap_cny": csi500_multi_factor_strategy.DEFAULT_MIN_MARKET_CAP_CNY,
        "hold_buffer": csi500_multi_factor_strategy.DEFAULT_HOLD_BUFFER,
        "hold_bonus": csi500_multi_factor_strategy.DEFAULT_HOLD_BONUS,
        "risk_on_exposure": csi500_multi_factor_strategy.DEFAULT_RISK_ON_EXPOSURE,
        "soft_defense_exposure": csi500_multi_factor_strategy.DEFAULT_SOFT_DEFENSE_EXPOSURE,
        "hard_defense_exposure": csi500_multi_factor_strategy.DEFAULT_HARD_DEFENSE_EXPOSURE,
        "soft_breadth_threshold": csi500_multi_factor_strategy.DEFAULT_SOFT_BREADTH_THRESHOLD,
        "hard_breadth_threshold": csi500_multi_factor_strategy.DEFAULT_HARD_BREADTH_THRESHOLD,
        "execution_cash_reserve_ratio": csi500_multi_factor_strategy.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
        "rebalance_frequency": "monthly",
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
    cn_dividend_quality_snapshot_manifest.profile: cn_dividend_quality_snapshot_manifest,
    cn_stock_momentum_rotation_manifest.profile: cn_stock_momentum_rotation_manifest,
    cn_csi500_multi_factor_snapshot_manifest.profile: cn_csi500_multi_factor_snapshot_manifest,
    cn_equity_combo_manifest.profile: cn_equity_combo_manifest,
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
    "CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE",
    "CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE",
    "CN_INDUSTRY_ETF_ROTATION_PROFILE",
    "CN_STOCK_MOMENTUM_ROTATION_PROFILE",
    "CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE",
    "CN_EQUITY_COMBO_PROFILE",
    "MANIFESTS",
    "get_strategy_manifest",
    "cn_csi500_multi_factor_snapshot_manifest",
    "cn_dividend_quality_snapshot_manifest",
    "cn_equity_combo_manifest",
    "cn_index_etf_tactical_rotation_manifest",
    "cn_industry_etf_rotation_aggressive_manifest",
    "cn_industry_etf_rotation_manifest",
    "cn_stock_momentum_rotation_manifest",
]
