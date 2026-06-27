from __future__ import annotations

from cn_equity_strategies.catalog import CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE
from cn_equity_strategies.runtime_adapters import (
    describe_platform_runtime_requirements,
    get_platform_runtime_adapter,
)


def test_index_etf_rotation_runtime_adapter_uses_market_history():
    adapter = get_platform_runtime_adapter(CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE, platform_id="qmt")

    assert adapter.available_inputs == frozenset({"market_history"})
    assert adapter.available_capabilities == frozenset({"broker_client"})
    assert adapter.require_snapshot_manifest is False


def test_index_etf_rotation_runtime_requirements_are_direct_inputs():
    requirements = describe_platform_runtime_requirements(
        CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
        platform_id="qmt",
    )

    assert requirements["profile_group"] == "direct_runtime_inputs"
    assert requirements["input_mode"] == "market_history"
    assert requirements["requires_snapshot_artifacts"] is False
    assert requirements["requires_snapshot_manifest_path"] is False
    assert requirements["snapshot_contract_version"] is None
