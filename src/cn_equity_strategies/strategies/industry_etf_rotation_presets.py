from __future__ import annotations

from typing import Any, Literal

from cn_equity_strategies.strategies import industry_etf_rotation_core as core

ProfileVariant = Literal["conservative_v1", "aggressive_research"]

# Hard-tech / CPO-adjacent sleeve for aggressive research (not runtime default).
TECH_THEME_SLEEVE_SYMBOLS = (
    "159994",  # Communication / optical chain proxy
    "512760",  # Semiconductor
    "159995",  # Chip
    "159819",  # AI
    "588000",  # STAR50
)

CONSERVATIVE_V1_PRESET: dict[str, Any] = {
    "profile_variant": "conservative_v1",
    "label": "Conservative v1 — pure momentum industry rotation",
    "universe_symbols": core.DEFAULT_UNIVERSE_SYMBOLS,
    "defensive_symbols": core.DEFAULT_DEFENSIVE_SYMBOLS,
    "benchmark_symbol": core.DEFAULT_BENCHMARK_SYMBOL,
    "enable_benchmark_risk_off": False,
    "momentum_window_days": core.DEFAULT_MOMENTUM_WINDOW_DAYS,
    "trend_window_days": core.DEFAULT_TREND_WINDOW_DAYS,
    "benchmark_trend_window_days": core.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
    "volatility_window_days": core.DEFAULT_VOLATILITY_WINDOW_DAYS,
    "top_n": core.DEFAULT_TOP_N,
    "min_momentum": core.DEFAULT_MIN_MOMENTUM,
    "rebalance_frequency": core.DEFAULT_REBALANCE_FREQUENCY,
    "weighting_mode": core.DEFAULT_WEIGHTING_MODE,
    "target_annual_volatility": core.DEFAULT_TARGET_ANNUAL_VOLATILITY,
    "max_gross_exposure": core.DEFAULT_MAX_GROSS_EXPOSURE,
    "min_history_days": core.DEFAULT_MIN_HISTORY_DAYS,
    "max_pair_correlation": core.DEFAULT_MAX_PAIR_CORRELATION,
    "sentiment_mode": "off",
    "execution_cash_reserve_ratio": core.DEFAULT_EXECUTION_CASH_RESERVE_RATIO,
}

# Research-only knobs; do not promote without beating conservative_v1 OOS with MDD gate.
AGGRESSIVE_RESEARCH_PRESETS: dict[str, dict[str, Any]] = {
    # --- Theme ETF sleeve (通信+半导体+AI+科创) ---
    "tech_sleeve_momentum_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — momentum / top3 / vol25% / monthly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 3,
        "target_annual_volatility": 0.25,
    },
    "tech_sleeve_top2_biweekly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — momentum / top2 / vol25% / biweekly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 2,
        "target_annual_volatility": 0.25,
        "rebalance_frequency": "biweekly",
    },
    "tech_sleeve_top2_biweekly_vol20": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — momentum / top2 / vol20% / biweekly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 2,
        "rebalance_frequency": "biweekly",
    },
    "tech_sleeve_sentiment_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — flow sentiment / top3 / monthly (default weight)",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 3,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow",
    },
    "tech_sleeve_sentiment_tuned_light": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — flow sentiment weight=0.08 / top3 / monthly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 3,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow",
        "sentiment_weight": 0.08,
    },
    "tech_sleeve_sentiment_tuned_heavy": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — flow sentiment weight=0.25 / top3 / monthly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 3,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow",
        "sentiment_weight": 0.25,
    },
    "tech_sleeve_crowding_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Tech sleeve — flow+crowding / top3 / monthly",
        "universe_symbols": TECH_THEME_SLEEVE_SYMBOLS,
        "top_n": 3,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow_crowding",
    },
    # --- Full 14-ETF pool variants ---
    "full_pool_sentiment_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — flow sentiment / monthly (default weight)",
        "sentiment_mode": "flow",
    },
    "full_pool_sentiment_tuned_light": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — flow sentiment weight=0.08 / monthly",
        "sentiment_mode": "flow",
        "sentiment_weight": 0.08,
    },
    "full_pool_sentiment_tuned_heavy": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — flow sentiment weight=0.25 / monthly",
        "sentiment_mode": "flow",
        "sentiment_weight": 0.25,
    },
    "full_pool_crowding_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — flow+crowding / monthly",
        "sentiment_mode": "flow_crowding",
    },
    "full_pool_momentum_biweekly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — momentum / biweekly",
        "rebalance_frequency": "biweekly",
    },
    "full_pool_vol25_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — momentum / vol25% / monthly",
        "target_annual_volatility": 0.25,
    },
    "full_pool_riskoff_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Full pool — MA200 benchmark risk-off / monthly",
        "enable_benchmark_risk_off": True,
    },
}

# Registered research profile preset (passed promotion gate vs conservative v1 OOS).
AGGRESSIVE_V1_PRESET: dict[str, Any] = {
    **CONSERVATIVE_V1_PRESET,
    "profile_variant": "aggressive_v1",
    "label": "Aggressive v1 — full pool vol25% monthly",
    "target_annual_volatility": 0.25,
}

# Keep matrix key aligned with registered preset.
AGGRESSIVE_RESEARCH_PRESETS["full_pool_vol25_monthly"] = {
    **AGGRESSIVE_V1_PRESET,
    "profile_variant": "aggressive_research",
}

# 光模块 / 算力主题个股（research-only；当前 fhps/成分非 PIT，存在幸存者偏差）
OPTICAL_COMPUTE_STOCK_SYMBOLS = (
    "300308",  # 中际旭创
    "300502",  # 新易盛
    "002281",  # 光迅科技
    "300394",  # 天孚通信
    "603083",  # 剑桥科技
    "601138",  # 工业富联
    "002463",  # 沪电股份
    "000977",  # 浪潮信息
)

STOCK_THEMATIC_PRESETS: dict[str, dict[str, Any]] = {
    "stock_optical_momentum_top2_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical/compute stocks — momentum top2 vol25% monthly",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.25,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_momentum_top2_biweekly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical/compute stocks — momentum top2 vol25% biweekly",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.25,
        "rebalance_frequency": "biweekly",
    },
    "stock_optical_momentum_top3_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical/compute stocks — momentum top3 vol25% monthly",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 3,
        "target_annual_volatility": 0.25,
    },
    "stock_optical_sentiment_top2_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical/compute stocks — flow sentiment top2 vol25% monthly",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow",
    },
    "stock_optical_sentiment_tuned_top2": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical/compute stocks — flow weight=0.08 top2 monthly",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.25,
        "sentiment_mode": "flow",
        "sentiment_weight": 0.08,
    },
}

PROMOTION_GATE = {
    "baseline_variant": "conservative_v1",
    "min_oos_total_return_lift": 0.05,
    "max_mdd_regression": 0.05,
    "oos_period": ("2024-01-01", "2026-06-27"),
    "train_period": ("2021-01-01", "2023-12-31"),
}

__all__ = [
    "AGGRESSIVE_RESEARCH_PRESETS",
    "AGGRESSIVE_V1_PRESET",
    "CONSERVATIVE_V1_PRESET",
    "OPTICAL_COMPUTE_STOCK_SYMBOLS",
    "PROMOTION_GATE",
    "STOCK_THEMATIC_PRESETS",
    "TECH_THEME_SLEEVE_SYMBOLS",
    "ProfileVariant",
]
