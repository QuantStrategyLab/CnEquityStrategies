from __future__ import annotations

from quant_platform_kit.common.strategies import get_strategy_component_map

from cn_equity_strategies.catalog import (
    CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE,
    CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
    CN_EQUITY_COMBO_PROFILE,
    CN_EQUITY_DOMAIN,
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_PROFILE,
    CN_STOCK_MOMENTUM_ROTATION_PROFILE,
    get_compatible_platforms,
    get_direct_market_history_profiles,
    get_external_snapshot_scaffold_profiles,
    get_profile_aliases,
    get_research_backtest_only_profiles,
    get_runtime_enabled_profiles,
    get_snapshot_backed_profiles,
    get_strategy_definition,
    get_strategy_definitions,
    get_strategy_metadata,
    resolve_canonical_profile,
)


def test_catalog_declares_runtime_enabled_cn_strategies():
    catalog = get_strategy_definitions()
    assert set(catalog) == {
        CN_INDUSTRY_ETF_ROTATION_PROFILE,
        CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
        CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
        CN_STOCK_MOMENTUM_ROTATION_PROFILE,
        CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE,
        CN_EQUITY_COMBO_PROFILE,
    }

    industry_definition = catalog[CN_INDUSTRY_ETF_ROTATION_PROFILE]
    assert industry_definition.domain == CN_EQUITY_DOMAIN
    assert industry_definition.required_inputs == frozenset({"market_history"})
    assert get_compatible_platforms(CN_INDUSTRY_ETF_ROTATION_PROFILE) == frozenset({"qmt"})
    assert get_strategy_metadata(CN_INDUSTRY_ETF_ROTATION_PROFILE).status == "research_backtest_only"

    aggressive_definition = catalog[CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE]
    assert aggressive_definition.domain == CN_EQUITY_DOMAIN
    assert aggressive_definition.required_inputs == frozenset({"market_history"})
    assert get_compatible_platforms(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE) == frozenset({"qmt"})
    assert get_strategy_metadata(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE).status == "runtime_enabled"
    assert (
        get_strategy_definition(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE).default_config[
            "target_annual_volatility"
        ]
        == 0.25
    )

    etf_definition = catalog[CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE]
    assert etf_definition.domain == CN_EQUITY_DOMAIN
    assert etf_definition.required_inputs == frozenset({"market_history"})
    assert get_compatible_platforms(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE) == frozenset({"qmt"})
    assert get_strategy_metadata(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE).status == "research_backtest_only"

    dividend_definition = catalog[CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE]
    assert dividend_definition.domain == CN_EQUITY_DOMAIN
    assert dividend_definition.required_inputs == frozenset({"feature_snapshot"})
    assert get_strategy_metadata(CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE).status == "runtime_enabled"

    stock_momentum_definition = catalog[CN_STOCK_MOMENTUM_ROTATION_PROFILE]
    assert stock_momentum_definition.domain == CN_EQUITY_DOMAIN
    assert stock_momentum_definition.required_inputs == frozenset({"market_history"})
    assert get_compatible_platforms(CN_STOCK_MOMENTUM_ROTATION_PROFILE) == frozenset({"qmt"})
    assert get_strategy_metadata(CN_STOCK_MOMENTUM_ROTATION_PROFILE).status == "runtime_enabled"

    component_map = get_strategy_component_map(dividend_definition)
    assert component_map["signal_logic"].module_path == (
        "cn_equity_strategies.strategies.cn_dividend_quality_snapshot"
    )


def test_profile_groups_keep_runtime_and_scaffolds_separate():
    assert get_direct_market_history_profiles() == frozenset(
        {CN_INDUSTRY_ETF_ROTATION_PROFILE, CN_STOCK_MOMENTUM_ROTATION_PROFILE}
    )
    assert get_snapshot_backed_profiles() == frozenset(
        {CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE, CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE}
    )
    assert get_external_snapshot_scaffold_profiles() == frozenset({"cn_small_cap_quality_snapshot"})
    assert get_research_backtest_only_profiles() == frozenset(
        {
            CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
            CN_INDUSTRY_ETF_ROTATION_PROFILE,
        }
    )
    assert get_runtime_enabled_profiles() == frozenset(
        {
            CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
            CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
            CN_STOCK_MOMENTUM_ROTATION_PROFILE,
            CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE,
            CN_EQUITY_COMBO_PROFILE,
        }
    )
    assert get_external_snapshot_scaffold_profiles().isdisjoint(get_runtime_enabled_profiles())
    assert get_research_backtest_only_profiles().isdisjoint(get_runtime_enabled_profiles())


def test_canonical_profiles_resolve_without_legacy_aliases():
    assert get_profile_aliases() == {}
    assert resolve_canonical_profile("cn-industry-etf-rotation") == CN_INDUSTRY_ETF_ROTATION_PROFILE
    assert (
        resolve_canonical_profile("cn-industry-etf-rotation-aggressive")
        == CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE
    )
    assert resolve_canonical_profile("cn-index-etf-tactical-rotation") == CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE
    assert resolve_canonical_profile("cn-dividend-quality-snapshot") == CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE
    assert resolve_canonical_profile("cn-csi500-multi-factor-snapshot") == CN_CSI500_MULTI_FACTOR_SNAPSHOT_PROFILE


def test_research_scaffold_profile_is_not_in_runtime_catalog():
    import pytest

    with pytest.raises(ValueError):
        get_strategy_definition("cn_small_cap_quality_snapshot")
