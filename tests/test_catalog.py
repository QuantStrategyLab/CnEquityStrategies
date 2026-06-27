from __future__ import annotations

from quant_platform_kit.common.strategies import get_strategy_component_map

from cn_equity_strategies.catalog import (
    CN_EQUITY_DOMAIN,
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
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


def test_catalog_declares_runtime_enabled_cn_direct_strategy():
    catalog = get_strategy_definitions()
    assert set(catalog) == {CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE}
    definition = catalog[CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE]

    assert definition.domain == CN_EQUITY_DOMAIN
    assert definition.required_inputs == frozenset({"market_history"})
    assert definition.target_mode == "weight"
    assert get_compatible_platforms(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE) == frozenset({"qmt"})
    assert get_strategy_metadata(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE).status == "runtime_enabled"
    assert CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE in get_runtime_enabled_profiles()

    component_map = get_strategy_component_map(definition)
    assert component_map["signal_logic"].module_path == (
        "cn_equity_strategies.strategies.cn_index_etf_tactical_rotation"
    )


def test_profile_groups_keep_runtime_and_scaffolds_separate():
    assert get_direct_market_history_profiles() == frozenset({CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE})
    assert get_snapshot_backed_profiles() == frozenset()
    assert get_external_snapshot_scaffold_profiles() == frozenset({"cn_dividend_low_vol_quality_snapshot"})
    assert get_research_backtest_only_profiles() == frozenset()
    assert get_runtime_enabled_profiles() == frozenset({CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE})
    assert get_external_snapshot_scaffold_profiles().isdisjoint(get_runtime_enabled_profiles())


def test_canonical_profiles_resolve_without_legacy_aliases():
    assert get_profile_aliases() == {}
    assert resolve_canonical_profile("cn-index-etf-tactical-rotation") == CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE


def test_planned_snapshot_profile_is_not_in_runtime_catalog():
    import pytest

    with pytest.raises(ValueError):
        get_strategy_definition("cn_dividend_low_vol_quality_snapshot")
