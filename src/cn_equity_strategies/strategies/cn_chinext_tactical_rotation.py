from __future__ import annotations

from typing import Any

from cn_equity_strategies.strategies import etf_rotation_core as base

CN_EQUITY_DOMAIN = base.CN_EQUITY_DOMAIN
SIGNAL_SOURCE = base.SIGNAL_SOURCE
STATUS_ICON = base.STATUS_ICON
PROFILE_NAME = "cn_chinext_tactical_rotation"

CHINEXT_ETF_SYMBOL = base.CHINEXT_ETF_SYMBOL
MONEY_MARKET_ETF_SYMBOL = base.MONEY_MARKET_ETF_SYMBOL
GOVT_BOND_ETF_SYMBOL = base.GOVT_BOND_ETF_SYMBOL
DEFAULT_BENCHMARK_SYMBOL = base.CSI300_ETF_SYMBOL

DEFAULT_UNIVERSE_SYMBOLS = (CHINEXT_ETF_SYMBOL, "159949")
DEFAULT_DEFENSIVE_SYMBOLS = (MONEY_MARKET_ETF_SYMBOL, GOVT_BOND_ETF_SYMBOL)
DEFAULT_MOMENTUM_WINDOW_DAYS = base.DEFAULT_MOMENTUM_WINDOW_DAYS
DEFAULT_TREND_WINDOW_DAYS = base.DEFAULT_TREND_WINDOW_DAYS
DEFAULT_BENCHMARK_TREND_WINDOW_DAYS = base.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS
DEFAULT_VOLATILITY_WINDOW_DAYS = base.DEFAULT_VOLATILITY_WINDOW_DAYS
DEFAULT_TOP_N = 1
DEFAULT_MIN_MOMENTUM = base.DEFAULT_MIN_MOMENTUM
DEFAULT_REBALANCE_FREQUENCY = base.DEFAULT_REBALANCE_FREQUENCY
DEFAULT_WEIGHTING_MODE = base.DEFAULT_WEIGHTING_MODE
DEFAULT_TARGET_ANNUAL_VOLATILITY = 0.50
DEFAULT_MAX_GROSS_EXPOSURE = base.DEFAULT_MAX_GROSS_EXPOSURE
DEFAULT_MIN_HISTORY_DAYS = 201
DEFAULT_MAX_PAIR_CORRELATION = base.DEFAULT_MAX_PAIR_CORRELATION

normalize_symbol = base.normalize_symbol
normalize_universe_symbols = base.normalize_universe_symbols
build_close_matrix = base.build_close_matrix


def compute_latest_signal(market_history: Any, **kwargs: Any) -> dict[str, object]:
    kwargs.setdefault("universe_symbols", DEFAULT_UNIVERSE_SYMBOLS)
    kwargs.setdefault("defensive_symbols", DEFAULT_DEFENSIVE_SYMBOLS)
    kwargs.setdefault("benchmark_symbol", DEFAULT_BENCHMARK_SYMBOL)
    kwargs.setdefault("momentum_window_days", DEFAULT_MOMENTUM_WINDOW_DAYS)
    kwargs.setdefault("trend_window_days", DEFAULT_TREND_WINDOW_DAYS)
    kwargs.setdefault("benchmark_trend_window_days", DEFAULT_BENCHMARK_TREND_WINDOW_DAYS)
    kwargs.setdefault("volatility_window_days", DEFAULT_VOLATILITY_WINDOW_DAYS)
    kwargs.setdefault("top_n", DEFAULT_TOP_N)
    kwargs.setdefault("min_momentum", DEFAULT_MIN_MOMENTUM)
    kwargs.setdefault("weighting_mode", DEFAULT_WEIGHTING_MODE)
    kwargs.setdefault("target_annual_volatility", DEFAULT_TARGET_ANNUAL_VOLATILITY)
    kwargs.setdefault("max_gross_exposure", DEFAULT_MAX_GROSS_EXPOSURE)
    kwargs.setdefault("min_history_days", DEFAULT_MIN_HISTORY_DAYS)
    kwargs.setdefault("max_pair_correlation", DEFAULT_MAX_PAIR_CORRELATION)
    return base.compute_latest_signal(market_history, **kwargs)


def build_target_weights(market_history: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, object]]:
    signal = compute_latest_signal(market_history, **kwargs)
    return dict(signal["weights"]), signal


def extract_managed_symbols(*_args: Any, **kwargs: Any) -> tuple[str, ...]:
    offensive = normalize_universe_symbols(kwargs.get("universe_symbols") or DEFAULT_UNIVERSE_SYMBOLS)
    defensive = normalize_universe_symbols(kwargs.get("defensive_symbols") or DEFAULT_DEFENSIVE_SYMBOLS)
    return tuple(dict.fromkeys([*offensive, *defensive]))


def compute_signals(market_history: Any, _current_holdings: Any = None, **kwargs: Any):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)
    kwargs.pop("rebalance_frequency", None)
    weights, metadata = build_target_weights(market_history, **kwargs)
    selected = ",".join(weights) if weights else "cash"
    target_vol = metadata.get("target_annual_volatility")
    target_vol_text = "none" if target_vol is None else f"{float(target_vol):.0%}"
    signal_desc = (
        f"cn chiNext tactical rotation state={metadata['signal_state']} selected={selected} "
        f"gross={metadata['gross_exposure']:.0%} cash={metadata['cash_weight']:.0%} "
        f"target_vol={target_vol_text} benchmark_risk_off={metadata['benchmark_risk_off']}"
    )
    status_desc = (
        f"state={metadata['signal_state']} | selected={selected} | "
        f"momentum={metadata['momentum_window_days']}d | trend={metadata['trend_window_days']}d | "
        f"benchmark={metadata.get('benchmark_symbol') or 'none'} | target_vol={target_vol_text}"
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
        },
    )
