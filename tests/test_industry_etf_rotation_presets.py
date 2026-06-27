from __future__ import annotations

from cn_equity_strategies.strategies import cn_industry_etf_rotation as profile
from cn_equity_strategies.strategies.industry_etf_rotation_presets import (
    AGGRESSIVE_RESEARCH_PRESETS,
    CONSERVATIVE_V1_PRESET,
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
