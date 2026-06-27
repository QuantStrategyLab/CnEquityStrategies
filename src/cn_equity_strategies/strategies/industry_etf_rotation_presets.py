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

# Defensive / risk-control variants for optical-compute stock sleeve (research matrix).
STOCK_THEMATIC_RISK_PRESETS: dict[str, dict[str, Any]] = {
    "stock_optical_vol20_top2_monthly": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks — vol20% top2 monthly (lower vol target)",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.20,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_vol18_top2_low_gross": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks — vol18% top2 max_gross 75%",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.18,
        "max_gross_exposure": 0.75,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_top2_tight_corr": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks — top2 max_pair_corr 0.70 vol20%",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "target_annual_volatility": 0.20,
        "max_pair_correlation": 0.70,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_top2_benchmark_riskoff": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks — top2 + CSI300 MA200 risk-off",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": ("510300",),
        "benchmark_symbol": "510300",
        "enable_benchmark_risk_off": True,
        "top_n": 2,
        "target_annual_volatility": 0.20,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_hybrid_etf_sleeve": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks + 510300/512760 hybrid top3 risk-off",
        "universe_symbols": tuple(
            dict.fromkeys([*OPTICAL_COMPUTE_STOCK_SYMBOLS, "510300", "512760"])
        ),
        "defensive_symbols": ("510300",),
        "benchmark_symbol": "510300",
        "enable_benchmark_risk_off": True,
        "top_n": 3,
        "target_annual_volatility": 0.20,
        "max_gross_exposure": 0.85,
        "rebalance_frequency": "monthly",
    },
    "stock_optical_top2_min_momentum": {
        **CONSERVATIVE_V1_PRESET,
        "profile_variant": "aggressive_research",
        "label": "Optical stocks — top2 min_momentum 5% vol20%",
        "universe_symbols": OPTICAL_COMPUTE_STOCK_SYMBOLS,
        "defensive_symbols": (),
        "benchmark_symbol": None,
        "top_n": 2,
        "min_momentum": 0.05,
        "target_annual_volatility": 0.20,
        "rebalance_frequency": "monthly",
    },
}

STOCK_THEMATIC_RESEARCH_MATRIX: dict[str, dict[str, Any]] = {
    **STOCK_THEMATIC_PRESETS,
    **STOCK_THEMATIC_RISK_PRESETS,
}

PROMOTION_GATE = {
    "baseline_variant": "conservative_v1",
    "min_oos_total_return_lift": 0.05,
    "max_mdd_regression": 0.05,
    "oos_period": ("2024-01-01", "2026-06-27"),
    "train_period": ("2021-01-01", "2023-12-31"),
}

# Stricter gate for single-name thematic sleeves (drawdown + bear-market caps).
STOCK_THEMATIC_PROMOTION_GATE: dict[str, Any] = {
    **PROMOTION_GATE,
    "max_mdd_absolute": -0.28,
    "max_bear_total_return_regression": 0.15,
    "bear_period": ("2021-01-01", "2022-12-31"),
}

# Human + automated checklist for promoting aggressive ETF profile to runtime.
AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST: dict[str, Any] = {
    "target_profile": "cn_industry_etf_rotation_aggressive",
    "baseline_profile": "cn_industry_etf_rotation",
    "preset_key": "full_pool_vol25_monthly",
    "automated_gate": PROMOTION_GATE,
    "evidence_required": [
        {
            "id": "oos_lift",
            "status": "pass",
            "note": "OOS 2024–2026 total return +5.4pp vs conservative v1 (matrix 2026-06-27)",
        },
        {
            "id": "mdd_parity",
            "status": "pass",
            "note": "Full-sample MDD -15.42% identical to conservative v1",
        },
        {
            "id": "bear_2021_2022",
            "status": "review",
            "note": "Confirm bear sub-period not worse than conservative by >5pp",
        },
        {
            "id": "live_dry_run",
            "status": "pass",
            "note": "Qmt e2e smoke on conservative; aggressive uses same entrypoint shape",
        },
        {
            "id": "runtime_policy",
            "status": "pending",
            "note": "Decide: replace default vs optional second QMT target vs stay research-only",
        },
        {
            "id": "pin_and_docs",
            "status": "pass",
            "note": "QmtPlatform pin merged; design doc §12–§13",
        },
    ],
    "rollout_options": [
        {
            "id": "optional_target",
            "label": "Add QMT target cn_industry_etf_rotation_aggressive (recommended first step)",
            "risk": "low",
        },
        {
            "id": "promote_default",
            "label": "Replace cn_industry_etf_rotation as platform default",
            "risk": "medium",
        },
        {
            "id": "stay_research",
            "label": "Keep research_backtest_only until dual-track combo is validated live",
            "risk": "lowest",
        },
    ],
    "recommended_rollout": "optional_target",
}

# Dual-track combo (return-level blend) — research profile spec; not yet a runtime entrypoint.
DUAL_TRACK_COMBO_PRESETS: dict[str, dict[str, Any]] = {
    "conservative_expanded_70_30": {
        "label": "70/30 industry conservative + expanded dividend",
        "industry_profile": "conservative",
        "industry_weight": 0.70,
        "dividend_weight": 0.30,
        "dividend_universe_mode": "expanded",
        "expanded_top_n": 40,
        "research_evidence": {
            "period": "2017-2026",
            "combo_ann": 0.1622,
            "combo_mdd": -0.1537,
            "combo_total": 0.697,
        },
    },
    "aggressive_expanded_70_30": {
        "label": "70/30 industry aggressive vol25% + expanded dividend",
        "industry_profile": "aggressive",
        "industry_weight": 0.70,
        "dividend_weight": 0.30,
        "dividend_universe_mode": "expanded",
        "expanded_top_n": 40,
        "research_evidence": {
            "period": "2017-2026",
            "combo_ann": 0.1295,
            "combo_mdd": -0.1537,
            "combo_total": 0.741,
        },
    },
}

DUAL_TRACK_PROMOTION_REVIEW_CHECKLIST: dict[str, Any] = {
    "target_profile": "cn_dual_track_combo",
    "status": "design_only",
    "blocking_items": [
        "Unified multi-asset simulator (not return-level blend)",
        "Expanded dividend PIT fhps/as_of selection in Pipeline",
        "Snapshot refresh cadence + QMT target wiring for combo weights",
        "Evidence gate: combo MDD <= industry leg MDD + 2pp on 2017+ sample",
    ],
    "candidate_presets": list(DUAL_TRACK_COMBO_PRESETS.keys()),
    "recommended_first_runtime_shape": {
        "profile": "cn_dual_track_combo",
        "legs": [
            {"profile": "cn_industry_etf_rotation", "weight": 0.70},
            {"profile": "cn_dividend_quality_snapshot", "weight": 0.30},
        ],
        "dividend_universe_mode": "expanded",
    },
}

__all__ = [
    "AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST",
    "AGGRESSIVE_RESEARCH_PRESETS",
    "AGGRESSIVE_V1_PRESET",
    "CONSERVATIVE_V1_PRESET",
    "DUAL_TRACK_COMBO_PRESETS",
    "DUAL_TRACK_PROMOTION_REVIEW_CHECKLIST",
    "OPTICAL_COMPUTE_STOCK_SYMBOLS",
    "PROMOTION_GATE",
    "STOCK_THEMATIC_PRESETS",
    "STOCK_THEMATIC_PROMOTION_GATE",
    "STOCK_THEMATIC_RESEARCH_MATRIX",
    "STOCK_THEMATIC_RISK_PRESETS",
    "TECH_THEME_SLEEVE_SYMBOLS",
    "ProfileVariant",
]
