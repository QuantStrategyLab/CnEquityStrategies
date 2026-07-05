from __future__ import annotations

import pandas as pd

from cn_equity_strategies.strategies import cn_equity_combo

from tests.test_cn_dividend_quality_snapshot import sample_factor_snapshot
from tests.test_cn_industry_etf_rotation import _history


def _combo_history() -> pd.DataFrame:
    history = _history()
    dates = sorted(history["date"].unique())
    price = 4.0
    rows = []
    for idx, day in enumerate(dates):
        price *= 1.0001 + (idx % 5) * 0.00003
        rows.append({"date": day, "symbol": "510300", "close": price, "volume": 2_000_000.0})
    return pd.concat([history, pd.DataFrame(rows)], ignore_index=True)


def test_cn_equity_combo_default_stock_leg_builds_weights() -> None:
    weights, metadata = cn_equity_combo.build_target_weights(
        market_history=_combo_history(),
        feature_snapshot=sample_factor_snapshot(),
    )

    assert weights
    assert metadata["legs"]["stock"]["weights"]
    assert "pit_index_code" not in cn_equity_combo.GROWTH_DEFAULT_CONFIG.get("chinext", {})
