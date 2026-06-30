"""CN equity combo manifests."""
from __future__ import annotations
from quant_platform_kit.strategy_contracts import StrategyManifest
from cn_equity_strategies.strategies import cn_equity_combo

CN_EQUITY_COMBO_PROFILE = cn_equity_combo.PROFILE_NAME

cn_equity_combo_manifest = StrategyManifest(
    profile=CN_EQUITY_COMBO_PROFILE,
    domain="cn_equity",
    display_name="CN Equity Combo",
    description="CN equity combo: ETF rotation (30%) + stock momentum (50%) + dividend quality (20%)",
    aliases=(),
    required_inputs=frozenset({"market_history", "feature_snapshot"}),
    default_config={"etf_weight": 0.30, "stock_weight": 0.50, "dividend_weight": 0.20, "execution_cash_reserve_ratio": 0.02, "rebalance_frequency": "monthly"},
)

__all__ = ["CN_EQUITY_COMBO_PROFILE", "cn_equity_combo_manifest"]
