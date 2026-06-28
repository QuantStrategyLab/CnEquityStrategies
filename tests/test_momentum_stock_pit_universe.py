from __future__ import annotations

import pandas as pd
import pytest

from cn_equity_strategies.research import momentum_stock_universe as universe
from cn_equity_strategies.strategies.etf_rotation_core import apply_max_single_name_weight_cap


def test_index_constituents_as_of_filters_future_inclusions(monkeypatch: pytest.MonkeyPatch):
    table = pd.DataFrame(
        {
            "symbol": ["600519", "000001", "300750"],
            "inclusion_date": pd.to_datetime(["2018-06-15", "2020-12-14", "2025-06-16"]),
        }
    )
    monkeypatch.setattr(universe, "_load_index_inclusion_table", lambda _code: table)
    members = universe.index_constituents_as_of(universe.CSI500_INDEX_CODE, "2021-01-01")
    assert members == ("600519", "000001")


def test_filter_offensive_for_pit_grandfathers_long_history(monkeypatch: pytest.MonkeyPatch):
    table = pd.DataFrame(
        {
            "symbol": ["600519", "300750"],
            "inclusion_date": pd.to_datetime(["2018-06-15", "2025-06-16"]),
        }
    )
    monkeypatch.setattr(universe, "_load_index_inclusion_table", lambda _code: table)
    history = pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-02", periods=260),
            "symbol": "600519",
            "close": 100.0,
        }
    )
    kept = universe.filter_offensive_for_pit(
        ("600519", "300750"),
        pit_index_code=universe.CSI500_INDEX_CODE,
        as_of="2021-06-01",
        market_history=history,
        min_history_days=220,
    )
    assert kept == ("600519",)


def test_resolve_momentum_stock_universe_csi500_pit_download_pool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(universe, "fetch_index_constituents", lambda _code: ("600519", "000001"))
    assert universe.resolve_momentum_stock_universe("csi500_pit") == ("600519", "000001")


def test_apply_max_single_name_weight_cap_limits_each_name():
    weights = {"A": 0.40, "B": 0.35, "C": 0.25}
    capped = apply_max_single_name_weight_cap(weights, max_single_name_weight=0.10)
    assert max(capped.values()) <= 0.10 + 1e-9
    assert sum(capped.values()) == pytest.approx(0.30)
