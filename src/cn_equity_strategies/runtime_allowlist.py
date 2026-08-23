"""Explicit runtime-selectable profiles for CN equity strategies."""

RUNTIME_SELECTABLE_ALLOWLIST_V1 = frozenset({"cn_industry_etf_rotation"})


def get_runtime_selectable_profiles() -> frozenset[str]:
    return RUNTIME_SELECTABLE_ALLOWLIST_V1
