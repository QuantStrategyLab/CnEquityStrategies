from __future__ import annotations

from cn_equity_strategies.catalog import (
    CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    get_qmt_rollout_allowlist,
    get_runtime_enabled_profiles,
)
from cn_equity_strategies.runtime_adapters import (
    describe_platform_runtime_requirements,
    get_platform_runtime_adapter,
)


def test_industry_etf_rotation_runtime_adapter_uses_market_history():
    adapter = get_platform_runtime_adapter(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"market_history"})
    assert adapter.available_capabilities == frozenset({"broker_client"})
    assert adapter.require_snapshot_manifest is False

    requirements = describe_platform_runtime_requirements(
        CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
        platform_id="qmt",
    )
    assert requirements["profile_group"] == "direct_runtime_inputs"
    assert requirements["input_mode"] == "market_history"


def test_aggressive_industry_etf_rotation_promoted_to_runtime():
    adapter = get_platform_runtime_adapter(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"market_history"})
    assert adapter.available_capabilities == frozenset({"broker_client"})
    assert CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE in get_runtime_enabled_profiles()
    assert CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE in get_qmt_rollout_allowlist()


def test_dividend_quality_runtime_adapter_requires_feature_snapshot_manifest():
    adapter = get_platform_runtime_adapter(CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"feature_snapshot"})
    assert adapter.require_snapshot_manifest is True
    assert adapter.snapshot_contract_version == "cn_dividend_quality_snapshot.factor_snapshot.v1"
    assert "roe_ttm" in adapter.required_feature_columns
    assert "is_st" in adapter.required_feature_columns


def test_dividend_quality_runtime_requirements_are_snapshot_backed():
    requirements = describe_platform_runtime_requirements(
        CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
        platform_id="qmt",
    )

    assert requirements["profile_group"] == "snapshot_backed"
    assert requirements["input_mode"] == "feature_snapshot"
    assert requirements["requires_snapshot_artifacts"] is True
    assert requirements["requires_snapshot_manifest_path"] is True
