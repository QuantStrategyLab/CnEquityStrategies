from __future__ import annotations

from typing import Any

from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as etf_leg
from cn_equity_strategies.strategies import industry_etf_rotation_core as stock_leg


def build_combo_target_weights(
    market_history: Any,
    current_holdings: Any = None,
    *,
    etf_config: dict | None = None,
    stock_config: dict | None = None,
    etf_weight: float = 0.30,
    stock_weight: float = 0.70,
    **kwargs: Any,
) -> tuple[dict[str, float], dict[str, object]]:
    """Unified dual-track combo signal: ETF leg + CSI500 stock leg.

    Calls the aggressive ETF rotation signal for the ETF leg and the
    industry-etf-rotation-core signal (stock universe) for the stock leg,
    then blends weights by ``etf_weight`` / ``stock_weight``.

    Parameters
    ----------
    market_history : pd.DataFrame
        Combined market history covering all symbols for both legs.
    current_holdings : ignored
        Placeholder for future incremental-rebalance use.
    etf_config : dict or None
        Keyword arguments forwarded to
        ``cn_industry_etf_rotation_aggressive.build_target_weights``.
        When ``None``, defaults to aggressive ETF defaults (vol25%,
        full pool, monthly).
    stock_config : dict or None
        Keyword arguments forwarded to
        ``industry_etf_rotation_core.build_target_weights`` for the stock
        leg.  When ``None``, defaults to CSI500 vol25 MA120 risk-off:
        universe=resolve_momentum_stock_universe("csi500"),
        defensive_symbols=("510300",), benchmark_symbol="510300",
        enable_benchmark_risk_off=True, benchmark_trend_window_days=120,
        top_n=5, target_annual_volatility=0.25, pit_index_code="000905".
    etf_weight : float
        Blending weight for the ETF leg (default 0.30).
    stock_weight : float
        Blending weight for the stock leg (default 0.70).
    **kwargs : Any
        Ignored (for compatibility with ``run_proxy_backtest`` which
        passes ``strategy_kwargs`` directly).

    Returns
    -------
    tuple[dict[str, float], dict[str, object]]
        Combined target-weights dict and merged metadata.
    """
    # --- ETF leg: aggressive rotation ---
    resolved_etf_config = _resolve_etf_config(etf_config)
    resolved_etf_config.pop("rebalance_frequency", None)
    etf_weights, etf_metadata = etf_leg.build_target_weights(
        market_history, **resolved_etf_config
    )

    # --- Stock leg: CSI500 cross-section momentum with MA120 risk-off ---
    resolved_stock_config = _resolve_stock_config(stock_config)
    resolved_stock_config.pop("rebalance_frequency", None)
    resolved_stock_config.pop("min_history_days", None)
    stock_raw_weights, stock_metadata = stock_leg.build_target_weights(
        market_history, **resolved_stock_config
    )

    # --- Combine weights ---
    all_symbols = set(etf_weights) | set(stock_raw_weights)
    combined: dict[str, float] = {}
    for symbol in all_symbols:
        ew = float(etf_weights.get(symbol, 0.0))
        sw = float(stock_raw_weights.get(symbol, 0.0))
        combined[symbol] = ew * etf_weight + sw * stock_weight

    # --- Merge metadata ---
    etf_meta = dict(etf_metadata or {})
    stock_meta = dict(stock_metadata or {})
    merged: dict[str, object] = {
        "etf_leg": {
            "weights": etf_weights,
            "signal_state": etf_meta.get("signal_state"),
            "gross_exposure": etf_meta.get("gross_exposure", 0.0),
            "cash_weight": etf_meta.get("cash_weight", 0.0),
            "top_n": etf_meta.get("top_n", 0),
        },
        "stock_leg": {
            "weights": stock_raw_weights,
            "signal_state": stock_meta.get("signal_state"),
            "gross_exposure": stock_meta.get("gross_exposure", 0.0),
            "cash_weight": stock_meta.get("cash_weight", 0.0),
            "top_n": stock_meta.get("top_n", 0),
        },
        "combo": {
            "weights": dict(combined),
            "etf_weight": etf_weight,
            "stock_weight": stock_weight,
        },
        "gross_exposure": sum(combined.values()),
    }

    return combined, merged


# ---------------------------------------------------------------------------
# Internal helpers — default config resolvers
# ---------------------------------------------------------------------------

_ETF_DEFAULTS: dict[str, Any] = {
    "target_annual_volatility": 0.25,
    "top_n": 5,
    "rebalance_frequency": "monthly",
    "sentiment_mode": "off",
    "enable_benchmark_risk_off": False,
}


def _resolve_etf_config(overrides: dict | None) -> dict[str, Any]:
    config = dict(_ETF_DEFAULTS)
    if overrides:
        config.update(overrides)
    return config


_STOCK_DEFAULTS: dict[str, Any] = {
    "defensive_symbols": ("510300",),
    "benchmark_symbol": "510300",
    "enable_benchmark_risk_off": True,
    "benchmark_trend_window_days": 120,
    "top_n": 5,
    "target_annual_volatility": 0.25,
    "pit_index_code": "000905",
    "sentiment_mode": "off",
    "rebalance_frequency": "monthly",
    "min_history_days": 220,
    "max_gross_exposure": 1.0,
    "max_pair_correlation": 0.85,
}


def _resolve_stock_config(overrides: dict | None) -> dict[str, Any]:
    config = dict(_STOCK_DEFAULTS)
    if overrides:
        config.update(overrides)
    return config
