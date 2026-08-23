from cn_equity_strategies.catalog import get_runtime_enabled_profiles
from cn_equity_strategies.runtime_allowlist import get_runtime_selectable_profiles


def test_legacy_runtime_entrypoint_reads_explicit_allowlist():
    assert get_runtime_enabled_profiles() == get_runtime_selectable_profiles()


def test_live_candidate_is_not_runtime_selectable():
    assert "cn_industry_etf_rotation_aggressive" not in get_runtime_selectable_profiles()
