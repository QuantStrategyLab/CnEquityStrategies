from __future__ import annotations

from cn_equity_strategies.strategies import cn_industry_etf_rotation as profile
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (
    AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST,
    AGGRESSIVE_RESEARCH_PRESETS,
    CONSERVATIVE_V1_PRESET,
    DUAL_TRACK_COMBO_PRESETS,
    STOCK_THEMATIC_RISK_PRESETS,
    TECH_THEME_SLEEVE_SYMBOLS,
)


def test_conservative_v1_matches_runtime_defaults():
    assert CONSERVATIVE_V1_PRESET["sentiment_mode"] == "off"
    assert CONSERVATIVE_V1_PRESET["enable_benchmark_risk_off"] is False
    assert CONSERVATIVE_V1_PRESET["top_n"] == profile.DEFAULT_TOP_N
    assert CONSERVATIVE_V1_PRESET["target_annual_volatility"] == profile.DEFAULT_TARGET_ANNUAL_VOLATILITY
    assert CONSERVATIVE_V1_PRESET["universe_symbols"] == profile.DEFAULT_UNIVERSE_SYMBOLS


def test_aggressive_presets_are_marked_research_only():
    for preset in AGGRESSIVE_RESEARCH_PRESETS.values():
        assert preset["profile_variant"] == "aggressive_research"


def test_tech_sleeve_is_subset_of_full_universe():
    full = set(profile.DEFAULT_UNIVERSE_SYMBOLS)
    assert set(TECH_THEME_SLEEVE_SYMBOLS).issubset(full)


def test_stock_risk_presets_lower_vol_or_add_controls():
    baseline = STOCK_THEMATIC_RISK_PRESETS["stock_optical_vol20_top2_monthly"]
    assert float(baseline["target_annual_volatility"]) <= 0.20
    riskoff = STOCK_THEMATIC_RISK_PRESETS["stock_optical_top2_benchmark_riskoff"]
    assert riskoff["enable_benchmark_risk_off"] is True
    assert riskoff["benchmark_symbol"] == "510300"


def test_aggressive_promotion_checklist_targets_registered_profile():
    assert AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST["target_profile"] == "cn_industry_etf_rotation_aggressive"
    assert AGGRESSIVE_PROMOTION_REVIEW_CHECKLIST["recommended_rollout"] == "optional_target"


def test_dual_track_combo_presets_declare_weights():
    preset = DUAL_TRACK_COMBO_PRESETS["conservative_expanded_70_30"]
    assert preset["industry_weight"] == 0.70
    assert preset["dividend_weight"] == 0.30

