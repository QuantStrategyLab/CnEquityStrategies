from __future__ import annotations

from typing import Any

from cn_equity_strategies.strategies import etf_rotation_core as base

CN_EQUITY_DOMAIN = base.CN_EQUITY_DOMAIN
SIGNAL_SOURCE = base.SIGNAL_SOURCE
STATUS_ICON = base.STATUS_ICON
PROFILE_NAME = "cn_index_etf_tactical_rotation"

CSI300_ETF_SYMBOL = base.CSI300_ETF_SYMBOL
CSI500_ETF_SYMBOL = base.CSI500_ETF_SYMBOL
CHINEXT_ETF_SYMBOL = base.CHINEXT_ETF_SYMBOL
STAR50_ETF_SYMBOL = base.STAR50_ETF_SYMBOL
CSI1000_ETF_SYMBOL = base.CSI1000_ETF_SYMBOL
HEALTHCARE_ETF_SYMBOL = base.HEALTHCARE_ETF_SYMBOL
NEW_ENERGY_ETF_SYMBOL = base.NEW_ENERGY_ETF_SYMBOL
SEMICONDUCTOR_ETF_SYMBOL = base.SEMICONDUCTOR_ETF_SYMBOL
GOLD_ETF_SYMBOL = base.GOLD_ETF_SYMBOL
NASDAQ_ETF_SYMBOL = base.NASDAQ_ETF_SYMBOL
MONEY_MARKET_ETF_SYMBOL = base.MONEY_MARKET_ETF_SYMBOL
GOVT_BOND_ETF_SYMBOL = base.GOVT_BOND_ETF_SYMBOL

DEFAULT_BENCHMARK_SYMBOL = base.DEFAULT_BENCHMARK_SYMBOL
DEFAULT_DEFENSIVE_SYMBOLS = base.DEFAULT_DEFENSIVE_SYMBOLS
DEFAULT_UNIVERSE_SYMBOLS = base.DEFAULT_UNIVERSE_SYMBOLS
DEFAULT_MOMENTUM_WINDOW_DAYS = base.DEFAULT_MOMENTUM_WINDOW_DAYS
DEFAULT_TREND_WINDOW_DAYS = base.DEFAULT_TREND_WINDOW_DAYS
DEFAULT_BENCHMARK_TREND_WINDOW_DAYS = base.DEFAULT_BENCHMARK_TREND_WINDOW_DAYS
DEFAULT_VOLATILITY_WINDOW_DAYS = base.DEFAULT_VOLATILITY_WINDOW_DAYS
DEFAULT_TOP_N = base.DEFAULT_TOP_N
DEFAULT_MIN_MOMENTUM = base.DEFAULT_MIN_MOMENTUM
DEFAULT_REBALANCE_FREQUENCY = base.DEFAULT_REBALANCE_FREQUENCY
DEFAULT_WEIGHTING_MODE = base.DEFAULT_WEIGHTING_MODE
DEFAULT_TARGET_ANNUAL_VOLATILITY = base.DEFAULT_TARGET_ANNUAL_VOLATILITY
DEFAULT_MAX_GROSS_EXPOSURE = base.DEFAULT_MAX_GROSS_EXPOSURE
DEFAULT_MIN_HISTORY_DAYS = base.DEFAULT_MIN_HISTORY_DAYS
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = base.DEFAULT_EXECUTION_CASH_RESERVE_RATIO

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
    return base.compute_latest_signal(market_history, **kwargs)


def build_target_weights(market_history: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, object]]:
    signal = compute_latest_signal(market_history, **kwargs)
    return dict(signal["weights"]), signal


def extract_managed_symbols(*_args: Any, **kwargs: Any) -> tuple[str, ...]:
    return base.extract_managed_symbols(
        universe_symbols=kwargs.get("universe_symbols") or DEFAULT_UNIVERSE_SYMBOLS,
        defensive_symbols=kwargs.get("defensive_symbols") or DEFAULT_DEFENSIVE_SYMBOLS,
    )


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
        f"cn index etf rotation state={metadata['signal_state']} selected={selected} "
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
