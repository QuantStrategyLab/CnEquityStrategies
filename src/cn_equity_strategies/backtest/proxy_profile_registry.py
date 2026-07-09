"""Registry of CN proxy-backtest compatible strategy profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ProxyProfileSpec:
    profile_name: str
    default_min_history_days: int
    build_target_weights: Callable[..., tuple[dict[str, float], dict[str, object]]]
    extract_managed_symbols: Callable[..., tuple[str, ...]]


def _spec(
    module: Any,
    *,
    profile_name: str,
    default_min_history_days: int,
) -> ProxyProfileSpec:
    return ProxyProfileSpec(
        profile_name=profile_name,
        default_min_history_days=default_min_history_days,
        build_target_weights=module.build_target_weights,
        extract_managed_symbols=module.extract_managed_symbols,
    )


def load_proxy_profile_registry() -> dict[str, ProxyProfileSpec]:
    from cn_equity_strategies.strategies import (
        cn_chinext_growth_momentum_quality,
        cn_chinext_tactical_rotation,
        cn_index_etf_tactical_rotation,
        cn_industry_etf_rotation,
        cn_industry_etf_rotation_aggressive,
        cn_star_growth_momentum_quality,
    )

    return {
        cn_index_etf_tactical_rotation.PROFILE_NAME: _spec(
            cn_index_etf_tactical_rotation,
            profile_name=cn_index_etf_tactical_rotation.PROFILE_NAME,
            default_min_history_days=cn_index_etf_tactical_rotation.DEFAULT_MIN_HISTORY_DAYS,
        ),
        cn_chinext_tactical_rotation.PROFILE_NAME: _spec(
            cn_chinext_tactical_rotation,
            profile_name=cn_chinext_tactical_rotation.PROFILE_NAME,
            default_min_history_days=cn_chinext_tactical_rotation.DEFAULT_MIN_HISTORY_DAYS,
        ),
        cn_chinext_growth_momentum_quality.PROFILE_NAME: _spec(
            cn_chinext_growth_momentum_quality,
            profile_name=cn_chinext_growth_momentum_quality.PROFILE_NAME,
            default_min_history_days=cn_chinext_growth_momentum_quality.DEFAULT_MIN_HISTORY_DAYS,
        ),
        cn_star_growth_momentum_quality.PROFILE_NAME: _spec(
            cn_star_growth_momentum_quality,
            profile_name=cn_star_growth_momentum_quality.PROFILE_NAME,
            default_min_history_days=cn_star_growth_momentum_quality.DEFAULT_MIN_HISTORY_DAYS,
        ),
        cn_industry_etf_rotation.PROFILE_NAME: _spec(
            cn_industry_etf_rotation,
            profile_name=cn_industry_etf_rotation.PROFILE_NAME,
            default_min_history_days=cn_industry_etf_rotation.DEFAULT_MIN_HISTORY_DAYS,
        ),
        cn_industry_etf_rotation_aggressive.PROFILE_NAME: _spec(
            cn_industry_etf_rotation_aggressive,
            profile_name=cn_industry_etf_rotation_aggressive.PROFILE_NAME,
            default_min_history_days=cn_industry_etf_rotation_aggressive.DEFAULT_MIN_HISTORY_DAYS,
        ),
    }


PROXY_PROFILE_REGISTRY = load_proxy_profile_registry()
SUPPORTED_PROFILES = frozenset(PROXY_PROFILE_REGISTRY.keys())

__all__ = ["ProxyProfileSpec", "PROXY_PROFILE_REGISTRY", "SUPPORTED_PROFILES", "load_proxy_profile_registry"]
