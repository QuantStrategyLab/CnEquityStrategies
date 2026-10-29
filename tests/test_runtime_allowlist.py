from cn_equity_strategies.catalog import get_runtime_enabled_profiles
from cn_equity_strategies.runtime_allowlist import get_runtime_selectable_profiles


def test_legacy_runtime_entrypoint_reads_explicit_allowlist():
    assert get_runtime_enabled_profiles() == get_runtime_selectable_profiles()


def test_live_candidate_is_not_runtime_selectable():
    assert "cn_industry_etf_rotation_aggressive" not in get_runtime_selectable_profiles()


def test_retired_profile_is_not_selectable_but_remains_resolvable():
    from cn_equity_strategies.catalog import (
        get_qmt_rollout_allowlist,
        get_strategy_definition,
        resolve_canonical_profile,
    )
    from cn_equity_strategies.runtime_adapters import PLATFORM_RUNTIME_ADAPTERS, get_platform_runtime_adapter

    assert get_runtime_enabled_profiles() == frozenset()
    assert get_qmt_rollout_allowlist() == frozenset()
    profile = "cn_industry_etf_rotation"
    assert resolve_canonical_profile(profile.replace("_", "-")) == profile
    assert get_strategy_definition(profile).profile == profile
    assert profile not in get_runtime_selectable_profiles()
    legacy = {profile, "cn_industry_etf_rotation_aggressive"}
    assert set(PLATFORM_RUNTIME_ADAPTERS["qmt"]) == legacy
    for legacy_profile in legacy:
        assert resolve_canonical_profile(legacy_profile.replace("_", "-")) == legacy_profile
        assert legacy_profile not in get_qmt_rollout_allowlist()
        assert get_platform_runtime_adapter(legacy_profile, platform_id="qmt") is not None
