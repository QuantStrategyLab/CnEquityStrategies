from __future__ import annotations

from typing import Any

from cn_equity_strategies.strategies import industry_etf_rotation_core as base

CN_EQUITY_DOMAIN = base.CN_EQUITY_DOMAIN
SIGNAL_SOURCE = base.SIGNAL_SOURCE
STATUS_ICON = base.STATUS_ICON
PROFILE_NAME = "cn_stock_momentum_rotation"

# No static DEFAULT_UNIVERSE_SYMBOLS — resolved at runtime via CSI500 constituents.
DEFAULT_DEFENSIVE_SYMBOLS = ("510300",)
DEFAULT_BENCHMARK_SYMBOL = "510300"
DEFAULT_MOMENTUM_WINDOW_DAYS = 60
DEFAULT_TREND_WINDOW_DAYS = 200
DEFAULT_BENCHMARK_TREND_WINDOW_DAYS = 120
DEFAULT_VOLATILITY_WINDOW_DAYS = 63
DEFAULT_TOP_N = 5
DEFAULT_MIN_MOMENTUM = 0.0
DEFAULT_REBALANCE_FREQUENCY = "monthly"
DEFAULT_WEIGHTING_MODE = "inverse_volatility"
DEFAULT_TARGET_ANNUAL_VOLATILITY: float | None = 0.25
DEFAULT_MAX_GROSS_EXPOSURE = 1.0
DEFAULT_MIN_HISTORY_DAYS = 220
DEFAULT_MAX_PAIR_CORRELATION = 0.85
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = 0.02
DEFAULT_ENABLE_BENCHMARK_RISK_OFF = True
DEFAULT_SENTIMENT_MODE: str = "off"

normalize_symbol = base.normalize_symbol
normalize_universe_symbols = base.normalize_universe_symbols
build_close_matrix = base.build_close_matrix
compute_turnover_surge_scores = base.compute_turnover_surge_scores


def _default_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs = {
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
        f"cn stock momentum rotation state={metadata['signal_state']} "
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
            "profile_variant": "stock_momentum_rotation",
        },
    )
