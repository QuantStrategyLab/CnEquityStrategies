from __future__ import annotations

from typing import Any

from cn_equity_strategies.strategies import cn_industry_etf_rotation as conservative
from cn_equity_strategies.strategies import industry_etf_rotation_core as base
from cn_equity_strategies.strategies.industry_etf_rotation_presets import AGGRESSIVE_V1_PRESET

CN_EQUITY_DOMAIN = conservative.CN_EQUITY_DOMAIN
SIGNAL_SOURCE = conservative.SIGNAL_SOURCE
STATUS_ICON = conservative.STATUS_ICON
PROFILE_NAME = "cn_industry_etf_rotation_aggressive"

DEFAULT_UNIVERSE_SYMBOLS = conservative.DEFAULT_UNIVERSE_SYMBOLS
DEFAULT_DEFENSIVE_SYMBOLS = conservative.DEFAULT_DEFENSIVE_SYMBOLS
DEFAULT_BENCHMARK_SYMBOL = conservative.DEFAULT_BENCHMARK_SYMBOL
DEFAULT_MOMENTUM_WINDOW_DAYS = conservative.DEFAULT_MOMENTUM_WINDOW_DAYS
DEFAULT_TREND_WINDOW_DAYS = conservative.DEFAULT_TREND_WINDOW_DAYS
DEFAULT_BENCHMARK_TREND_WINDOW_DAYS = conservative.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS
DEFAULT_VOLATILITY_WINDOW_DAYS = conservative.DEFAULT_VOLATILITY_WINDOW_DAYS
DEFAULT_TOP_N = conservative.DEFAULT_TOP_N
DEFAULT_MIN_MOMENTUM = conservative.DEFAULT_MIN_MOMENTUM
DEFAULT_REBALANCE_FREQUENCY = conservative.DEFAULT_REBALANCE_FREQUENCY
DEFAULT_WEIGHTING_MODE = conservative.DEFAULT_WEIGHTING_MODE
DEFAULT_TARGET_ANNUAL_VOLATILITY = float(AGGRESSIVE_V1_PRESET["target_annual_volatility"])
DEFAULT_MAX_GROSS_EXPOSURE = conservative.DEFAULT_MAX_GROSS_EXPOSURE
DEFAULT_MIN_HISTORY_DAYS = conservative.DEFAULT_MIN_HISTORY_DAYS
DEFAULT_MAX_PAIR_CORRELATION = conservative.DEFAULT_MAX_PAIR_CORRELATION
DEFAULT_ENABLE_BENCHMARK_RISK_OFF = conservative.DEFAULT_ENABLE_BENCHMARK_RISK_OFF
DEFAULT_SENTIMENT_MODE = conservative.DEFAULT_SENTIMENT_MODE
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = conservative.DEFAULT_EXECUTION_CASH_RESERVE_RATIO

normalize_symbol = conservative.normalize_symbol
normalize_universe_symbols = conservative.normalize_universe_symbols
build_close_matrix = conservative.build_close_matrix
compute_turnover_surge_scores = conservative.compute_turnover_surge_scores


def _default_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs = {
        "universe_symbols": DEFAULT_UNIVERSE_SYMBOLS,
        "defensive_symbols": DEFAULT_DEFENSIVE_SYMBOLS,
        "benchmark_symbol": DEFAULT_BENCHMARK_SYMBOL,
        "enable_benchmark_risk_off": DEFAULT_ENABLE_BENCHMARK_RISK_OFF,
        "momentum_window_days": DEFAULT_MOMENTUM_WINDOW_DAYS,
        "trend_window_days": DEFAULT_TREND_WINDOW_DAYS,
        "benchmark_trend_window_days": DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
        "volatility_window_days": DEFAULT_VOLATILITY_WINDOW_DAYS,
        "top_n": DEFAULT_TOP_N,
        "min_momentum": DEFAULT_MIN_MOMENTUM,
        "weighting_mode": DEFAULT_WEIGHTING_MODE,
        "target_annual_volatility": DEFAULT_TARGET_ANNUAL_VOLATILITY,
        "max_gross_exposure": DEFAULT_MAX_GROSS_EXPOSURE,
        "min_history_days": DEFAULT_MIN_HISTORY_DAYS,
        "max_pair_correlation": DEFAULT_MAX_PAIR_CORRELATION,
        "sentiment_mode": DEFAULT_SENTIMENT_MODE,
    }
    kwargs.update(overrides)
    return kwargs


def compute_latest_signal(market_history: Any, **kwargs: Any) -> dict[str, object]:
    return base.compute_latest_signal(market_history, **_default_kwargs(**kwargs))


def build_target_weights(market_history: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, object]]:
    signal = compute_latest_signal(market_history, **kwargs)
    return dict(signal["weights"]), signal


def extract_managed_symbols(*_args: Any, **kwargs: Any) -> tuple[str, ...]:
    return base.extract_managed_symbols(**_default_kwargs(**kwargs))


def compute_signals(market_history: Any, _current_holdings: Any = None, **kwargs: Any):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)
    kwargs.pop("rebalance_frequency", None)
    weights, metadata = build_target_weights(market_history, **kwargs)
    selected = ",".join(weights) if weights else "cash"
    signal_desc = (
        f"cn industry etf rotation aggressive state={metadata['signal_state']} "
        f"sentiment={metadata.get('sentiment_mode')} selected={selected} "
        f"gross={metadata['gross_exposure']:.0%} cash={metadata['cash_weight']:.0%}"
    )
    status_desc = (
        f"state={metadata['signal_state']} | sentiment={metadata.get('sentiment_mode')} | "
        f"selected={selected} | top_n={metadata['top_n']} | vol_target={DEFAULT_TARGET_ANNUAL_VOLATILITY:.0%}"
    )
    return (
        weights,
        signal_desc,
        bool(metadata["cash_weight"] > 1e-12),
        status_desc,
        {
            **metadata,
            "managed_symbols": extract_managed_symbols(**kwargs),
            "status_icon": STATUS_ICON,
            "signal_source": SIGNAL_SOURCE,
            "actionable": True,
            "profile_variant": "aggressive_v1",
        },
    )
