"""CN equity combo strategy — ETF rotation + stock momentum + dividend quality.

Combines three A-share sub-strategies into a single weight-allocated portfolio.

Static mode
-----------
Fixed weights per leg (default: 40/40/20 ETF/stock/dividend).

Dynamic mode
------------
Regime-based adjustment: when the dividend leg's breadth regime weakens,
reduce offensive (stock/ETF) weights proportionally.  The total offensive
allocation shifts to the safe-haven ETF (510300).

Usage
-----
from cn_equity_strategies.strategies.cn_equity_combo import compute_signals
"""

from __future__ import annotations

from typing import Any


from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_strategy
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as etf_strategy
from cn_equity_strategies.strategies import industry_etf_rotation_core as stock_strategy

CN_EQUITY_DOMAIN = "cn_equity"
SIGNAL_SOURCE = "combo"
STATUS_ICON = "🔀"
PROFILE_NAME = "cn_equity_combo"

# Default static weights
DEFAULT_ETF_WEIGHT = 0.40
DEFAULT_STOCK_WEIGHT = 0.40
DEFAULT_DIVIDEND_WEIGHT = 0.20

# Dynamic mode thresholds
DYNAMIC_SOFT_CUT = 0.15  # reduce offensive by 15% in soft_defense
DYNAMIC_HARD_CUT = 0.50  # reduce offensive by 50% in hard_defense

# ETF leg defaults
ETF_DEFAULT_CONFIG: dict[str, Any] = {
    "target_annual_volatility": 0.25,
    "top_n": 5,
    "sentiment_mode": "off",
    "enable_benchmark_risk_off": False,
}

# Stock momentum leg defaults (CSI500 vol25 MA120 risk-off)
STOCK_DEFAULT_CONFIG: dict[str, Any] = {
    "defensive_symbols": ("510300",),
    "benchmark_symbol": "510300",
    "enable_benchmark_risk_off": True,
    "benchmark_trend_window_days": 120,
    "top_n": 5,
    "target_annual_volatility": 0.25,
    "sentiment_mode": "off",
    "pit_index_code": "000905",
}

# Dividend leg defaults (current conservative)
DIVIDEND_DEFAULT_CONFIG: dict[str, Any] = {}


def _clean_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Remove combo-level keys before passing to sub-strategies."""
    ignored = {
        "etf_weight", "stock_weight", "dividend_weight",
        "dynamic_mode", "translator", "signal_text_fn",
        "execution_cash_reserve_ratio", "rebalance_frequency",
        "run_as_of",
    }
    return {k: v for k, v in kwargs.items() if k not in ignored}


def build_target_weights(
    market_history: Any = None,
    current_holdings: Any = None,
    *,
    feature_snapshot: Any = None,
    etf_weight: float = DEFAULT_ETF_WEIGHT,
    stock_weight: float = DEFAULT_STOCK_WEIGHT,
    dividend_weight: float = DEFAULT_DIVIDEND_WEIGHT,
    dynamic_mode: bool = True,
    etf_config: dict[str, Any] | None = None,
    stock_config: dict[str, Any] | None = None,
    dividend_config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[dict[str, float], dict[str, object]]:
    """Compute combined target weights from all three sub-strategies.

    Parameters
    ----------
    market_history : pd.DataFrame or None
        Required for ETF and stock legs.
    current_holdings : set[str] or None
        Currently held symbol set for hold-bonus logic.
    feature_snapshot : pd.DataFrame or None
        Required for dividend quality leg.
    etf_weight, stock_weight, dividend_weight : float
        Allocation weights for each leg.  Should sum to 1.0.
    dynamic_mode : bool
        If True, reduce offensive allocation when dividend leg signals
        market weakness (soft_defense / hard_defense regimes).
    etf_config, stock_config, dividend_config : dict or None
        Overrides passed to each sub-strategy's ``build_target_weights``.
    **kwargs : Any
        Ignored (compatibility with runtime entrypoint).
    """
    resolved_etf = dict(ETF_DEFAULT_CONFIG)
    resolved_etf.update(etf_config or {})

    resolved_stock = dict(STOCK_DEFAULT_CONFIG)
    resolved_stock.update(stock_config or {})

    resolved_dividend = dict(DIVIDEND_DEFAULT_CONFIG)
    resolved_dividend.update(dividend_config or {})

    # Compute each leg
    etf_weights: dict[str, float] = {}
    stock_raw_weights: dict[str, float] = {}
    dividend_weights: dict[str, float] = {}
    dividend_metadata: dict[str, object] = {}

    if market_history is not None:
        try:
            etf_weights, _ = etf_strategy.build_target_weights(
                market_history, **resolved_etf,
            )
        except Exception:
            etf_weights = {}

        try:
            stock_raw_weights, _ = stock_strategy.build_target_weights(
                market_history, **resolved_stock,
            )
        except Exception:
            stock_raw_weights = {}

    if feature_snapshot is not None:
        try:
            dividend_weights, _, dividend_metadata = dividend_strategy.build_target_weights(
                feature_snapshot,
                current_holdings=current_holdings,
                **resolved_dividend,
            )
        except Exception:
            dividend_weights = {}

    # Determine effective weights (dynamic adjustment)
    regime = str(dividend_metadata.get("regime", "risk_on"))
    if dynamic_mode and regime in ("soft_defense", "hard_defense"):
        cut = DYNAMIC_HARD_CUT if regime == "hard_defense" else DYNAMIC_SOFT_CUT
        effective_etf = etf_weight * (1.0 - cut)
        effective_stock = stock_weight * (1.0 - cut)
        effective_dividend = dividend_weight + (etf_weight + stock_weight) * cut
    else:
        effective_etf = etf_weight
        effective_stock = stock_weight
        effective_dividend = dividend_weight

    # Combine weights
    all_symbols = set(etf_weights) | set(stock_raw_weights) | set(dividend_weights)
    combined: dict[str, float] = {}
    for symbol in all_symbols:
        ew = etf_weights.get(symbol, 0.0)
        sw = stock_raw_weights.get(symbol, 0.0)
        dw = dividend_weights.get(symbol, 0.0)
        combined[symbol] = ew * effective_etf + sw * effective_stock + dw * effective_dividend

    # Normalize to ensure sum <= 1.0
    total = sum(combined.values())
    if total > 0.0:
        # Scale if exceeding 1.0 (shouldn't happen if weights sum to 1.0, but safe)
        scale = min(1.0, 1.0 / total) if total > 1.0 else 1.0
        if scale < 1.0:
            combined = {s: w * scale for s, w in combined.items()}

    metadata: dict[str, object] = {
        "combo": {
            "etf_weight": effective_etf,
            "stock_weight": effective_stock,
            "dividend_weight": effective_dividend,
        },
        "legs": {
            "etf": {"weights": etf_weights, "configured_weight": etf_weight},
            "stock": {"weights": stock_raw_weights, "configured_weight": stock_weight},
            "dividend": {
                "weights": dividend_weights,
                "configured_weight": dividend_weight,
                "regime": regime,
            },
        },
        "regime": regime,
        "dynamic_mode": dynamic_mode,
        "gross_exposure": sum(combined.values()),
        "selected_count": len(combined),
    }

    return combined, metadata


def extract_managed_symbols(*args: Any, **kwargs: Any) -> tuple[str, ...]:
    return ("510300",)


def compute_signals(
    market_history: Any = None,
    current_holdings: Any = None,
    *,
    feature_snapshot: Any = None,
    **kwargs: Any,
):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)

    weights, metadata = build_target_weights(
        market_history=market_history,
        current_holdings=current_holdings,
        feature_snapshot=feature_snapshot,
        **kwargs,
    )

    combo_meta = metadata.get("combo", {})
    regime = metadata.get("regime", "risk_on")
    selected = ",".join(weights.keys()) if weights else "cash"
    signal_desc = (
        f"cn combo regime={regime} selected={selected} "
        f"gross={metadata['gross_exposure']:.0%} "
        f"etf={combo_meta.get('etf_weight', 0):.0%} "
        f"stock={combo_meta.get('stock_weight', 0):.0%} "
        f"div={combo_meta.get('dividend_weight', 0):.0%}"
    )
    status_desc = (
        f"regime={regime} | "
        f"etf={combo_meta.get('etf_weight', 0):.0%} "
        f"stock={combo_meta.get('stock_weight', 0):.0%} "
        f"div={combo_meta.get('dividend_weight', 0):.0%}"
    )
    has_cash_residual = metadata["gross_exposure"] < 0.999

    return (
        weights,
        signal_desc,
        has_cash_residual,
        status_desc,
        {
            **metadata,
            "managed_symbols": extract_managed_symbols(),
            "status_icon": STATUS_ICON,
            "signal_source": SIGNAL_SOURCE,
            "actionable": True,
        },
    )
