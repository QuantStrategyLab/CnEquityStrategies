from __future__ import annotations

from dataclasses import replace

from quant_platform_kit.strategy_contracts import (
    StrategyRuntimeAdapter,
    validate_strategy_runtime_adapter,
)

from cn_equity_strategies.catalog import (
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE,
    get_strategy_definition,
    get_strategy_definitions,
    resolve_canonical_profile,
)
from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation as index_etf_strategy

QMT_PLATFORM = "qmt"
SUPPORTED_RUNTIME_PLATFORMS = frozenset({QMT_PLATFORM})

PLATFORM_NATIVE_TARGET_MODES: dict[str, str] = {
    QMT_PLATFORM: "weight",
}

BASE_RUNTIME_ADAPTERS: dict[str, StrategyRuntimeAdapter] = {
    CN_INDEX_ETF_TACTICAL_ROTATION_PROFILE: StrategyRuntimeAdapter(
        status_icon=index_etf_strategy.STATUS_ICON,
        managed_symbols_extractor=index_etf_strategy.extract_managed_symbols,
    ),
}


def _build_runtime_adapter_for_platform(
    profile: str,
    *,
    platform_id: str,
) -> StrategyRuntimeAdapter:
    canonical_profile = resolve_canonical_profile(profile)
    normalized_platform = str(platform_id).strip().lower()
    if normalized_platform not in SUPPORTED_RUNTIME_PLATFORMS:
        raise ValueError(f"Unsupported platform runtime adapter lookup for {platform_id!r}")

    definition = get_strategy_definition(canonical_profile)
    if normalized_platform not in definition.supported_platforms:
        raise ValueError(
            f"Strategy profile {canonical_profile!r} does not declare support for platform {platform_id!r}"
        )

    try:
        base_adapter = BASE_RUNTIME_ADAPTERS[canonical_profile]
    except KeyError as exc:
        raise ValueError(f"Strategy profile {canonical_profile!r} has no runtime adapter spec") from exc

    available_inputs = set(base_adapter.available_inputs or definition.required_inputs)
    available_inputs.update(definition.required_inputs)

    available_capabilities = set(base_adapter.available_capabilities)
    if normalized_platform == QMT_PLATFORM:
        available_capabilities.add("broker_client")

    return validate_strategy_runtime_adapter(
        replace(
            base_adapter,
            available_inputs=frozenset(available_inputs),
            available_capabilities=frozenset(available_capabilities),
            portfolio_input_name=base_adapter.portfolio_input_name,
        )
    )


def _build_platform_runtime_adapter_map(platform_id: str) -> dict[str, StrategyRuntimeAdapter]:
    normalized_platform = str(platform_id).strip().lower()
    adapters: dict[str, StrategyRuntimeAdapter] = {}
    for profile, definition in get_strategy_definitions().items():
        if normalized_platform not in definition.supported_platforms:
            continue
        adapters[profile] = _build_runtime_adapter_for_platform(
            profile,
            platform_id=normalized_platform,
        )
    return adapters


PLATFORM_RUNTIME_ADAPTERS: dict[str, dict[str, StrategyRuntimeAdapter]] = {
    platform_id: _build_platform_runtime_adapter_map(platform_id)
    for platform_id in sorted(SUPPORTED_RUNTIME_PLATFORMS)
}


def derive_runtime_input_mode(required_inputs: frozenset[str] | set[str] | tuple[str, ...]) -> str:
    normalized = frozenset(str(value).strip() for value in required_inputs)
    if normalized == frozenset({"feature_snapshot"}):
        return "feature_snapshot"
    if normalized == frozenset({"market_history"}):
        return "market_history"
    return "+".join(sorted(normalized)) or "none"


def describe_platform_runtime_requirements(profile: str | None, *, platform_id: str) -> dict[str, object]:
    canonical_profile = resolve_canonical_profile(profile)
    definition = get_strategy_definition(canonical_profile)
    adapter = get_platform_runtime_adapter(canonical_profile, platform_id=platform_id)
    requires_snapshot_artifacts = "feature_snapshot" in frozenset(definition.required_inputs)
    return {
        "input_mode": derive_runtime_input_mode(definition.required_inputs),
        "requires_snapshot_artifacts": requires_snapshot_artifacts,
        "requires_snapshot_manifest_path": bool(
            requires_snapshot_artifacts and adapter.require_snapshot_manifest
        ),
        "snapshot_contract_version": adapter.snapshot_contract_version,
        "requires_strategy_config_path": False,
        "config_source_policy": "none",
        "reconciliation_output_policy": "optional",
        "profile_group": "snapshot_backed" if requires_snapshot_artifacts else "direct_runtime_inputs",
    }


def get_platform_runtime_adapter(profile: str | None, *, platform_id: str) -> StrategyRuntimeAdapter:
    canonical_profile = resolve_canonical_profile(profile)
    adapters = PLATFORM_RUNTIME_ADAPTERS.get(str(platform_id).strip().lower())
    if adapters is None:
        raise ValueError(f"Unsupported platform runtime adapter lookup for {platform_id!r}")
    try:
        adapter = adapters[canonical_profile]
    except KeyError as exc:
        raise ValueError(
            f"Strategy profile {canonical_profile!r} has no runtime adapter for platform {platform_id!r}"
        ) from exc
    return validate_strategy_runtime_adapter(adapter)


__all__ = [
    "BASE_RUNTIME_ADAPTERS",
    "PLATFORM_NATIVE_TARGET_MODES",
    "PLATFORM_RUNTIME_ADAPTERS",
    "QMT_PLATFORM",
    "SUPPORTED_RUNTIME_PLATFORMS",
    "derive_runtime_input_mode",
    "describe_platform_runtime_requirements",
    "get_platform_runtime_adapter",
]
