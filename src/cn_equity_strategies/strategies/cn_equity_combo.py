"""CN equity combo strategy — ETF rotation + stock momentum + dividend quality.

Combines three A-share sub-strategies into a single weight-allocated portfolio.
All sub-strategies imported from the pip-installable ``cn_equity_strategies``
package.

Static mode
-----------
Fixed weights per leg (default: 30/50/20 ETF/stock/dividend).

Dynamic mode
------------
Regime-based adjustment driven by the dividend leg's breadth regime:
- risk_on: full static weights (30/50/20 ETF/stock/dividend).
- soft_defense: stock reduced to 85% of its weight; freed allocation
  shifts to the safe-haven ETF (510300).
- hard_defense: stock reduced to 50% of its weight; ETF reduced to 85%
  of its weight; freed allocation stays in the safe-haven ETF.

Usage
-----
from quant_cn_combo_strategies.strategies.cn_equity_combo import compute_signals
"""

from __future__ import annotations

import logging
from typing import Any


from quant_platform_kit.common.strategies import compute_portfolio_drift

from cn_equity_strategies.strategies import cn_dividend_quality_snapshot as dividend_strategy

logger = logging.getLogger(__name__)
from cn_equity_strategies.strategies import cn_industry_etf_rotation_aggressive as etf_strategy
from cn_equity_strategies.strategies import industry_etf_rotation_core as stock_strategy

SIGNAL_SOURCE = "combo"
STATUS_ICON = "\U0001f500"
PROFILE_NAME = "cn_equity_combo"

# Default static weights
DEFAULT_ETF_WEIGHT = 0.30
DEFAULT_STOCK_WEIGHT = 0.50
DEFAULT_DIVIDEND_WEIGHT = 0.20
DEFAULT_REBALANCE_THRESHOLD = 0.05  # 5% drift triggers rebalance

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
        except Exception as exc:
            logger.error("ETF sub-strategy failed: %s", exc, exc_info=True)

        try:
            stock_raw_weights, _ = stock_strategy.build_target_weights(
                market_history, **resolved_stock,
            )
        except Exception as exc:
            logger.error("Stock sub-strategy failed: %s", exc, exc_info=True)

    if feature_snapshot is not None:
        try:
            dividend_weights, _, dividend_metadata = dividend_strategy.build_target_weights(
                feature_snapshot,
                current_holdings=current_holdings,
                **resolved_dividend,
            )
        except Exception as exc:
            logger.error("Dividend sub-strategy failed: %s", exc, exc_info=True)

    # Determine effective weights (dynamic adjustment)
    regime = str(dividend_metadata.get("regime", "risk_on"))
    if dynamic_mode and regime == "soft_defense":
        # Soft defense: reduce stock to 85%, shift proceeds to ETF
        effective_stock = stock_weight * 0.85
        effective_etf = etf_weight + (stock_weight - effective_stock)
        effective_dividend = dividend_weight
    elif dynamic_mode and regime == "hard_defense":
        # Hard defense: stock at 50%, ETF boosted to 85% allocation
        effective_stock = stock_weight * 0.50
        effective_etf = etf_weight * 0.85
        effective_dividend = dividend_weight
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
        "rebalance": compute_portfolio_drift(
            combined,
            holdings=kwargs.get("current_holdings_quantities", {}),
            prices=kwargs.get("current_prices", {}),
            threshold=float(kwargs.get("rebalance_threshold", DEFAULT_REBALANCE_THRESHOLD)),
        ),
    }

    return combined, metadata


# _check_drift removed — use quant_platform_kit.common.strategies.compute_portfolio_drift


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
        f"combo regime={regime} selected={selected} "
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
