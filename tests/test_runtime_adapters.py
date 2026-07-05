from __future__ import annotations

from cn_equity_strategies.catalog import (
    CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_PROFILE,
    CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
    CN_EQUITY_COMBO_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE,
    CN_INDUSTRY_ETF_ROTATION_PROFILE,
    CN_STAR_GROWTH_MOMENTUM_QUALITY_PROFILE,
    get_qmt_optional_runtime_profiles,
    get_qmt_rollout_allowlist,
)
from cn_equity_strategies.runtime_adapters import (
    describe_platform_runtime_requirements,
    get_platform_runtime_adapter,
)


def test_industry_etf_rotation_runtime_adapter_uses_market_history():
    adapter = get_platform_runtime_adapter(CN_INDUSTRY_ETF_ROTATION_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"market_history"})
    assert adapter.available_capabilities == frozenset({"broker_client"})
    assert adapter.require_snapshot_manifest is False

    requirements = describe_platform_runtime_requirements(
        CN_INDUSTRY_ETF_ROTATION_PROFILE,
        platform_id="qmt",
    )
    assert requirements["profile_group"] == "direct_runtime_inputs"
    assert requirements["input_mode"] == "market_history"


def test_aggressive_industry_etf_rotation_optional_qmt_runtime_adapter():
    adapter = get_platform_runtime_adapter(CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"market_history"})
    assert adapter.available_capabilities == frozenset({"broker_client"})
    assert CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE in get_qmt_optional_runtime_profiles()
    assert CN_INDUSTRY_ETF_ROTATION_AGGRESSIVE_PROFILE in get_qmt_rollout_allowlist()


def test_dividend_quality_runtime_adapter_requires_feature_snapshot_manifest():
    import pytest

    with pytest.raises(ValueError):
        get_platform_runtime_adapter(CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE, platform_id="qmt")


def test_combo_runtime_adapter_is_not_available_for_qmt():
    import pytest

    with pytest.raises(ValueError):
        get_platform_runtime_adapter(CN_EQUITY_COMBO_PROFILE, platform_id="qmt")


def test_growth_sleeves_are_not_available_for_qmt_runtime():
    import pytest

    with pytest.raises(ValueError):
        get_platform_runtime_adapter(CN_CHINEXT_GROWTH_MOMENTUM_QUALITY_PROFILE, platform_id="qmt")
    with pytest.raises(ValueError):
        get_platform_runtime_adapter(CN_STAR_GROWTH_MOMENTUM_QUALITY_PROFILE, platform_id="qmt")


def test_dividend_quality_runtime_requirements_are_snapshot_backed():
    import pytest

    with pytest.raises(ValueError):
        describe_platform_runtime_requirements(
            CN_DIVIDEND_QUALITY_SNAPSHOT_PROFILE,
            platform_id="qmt",
        )
