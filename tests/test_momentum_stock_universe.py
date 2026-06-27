from __future__ import annotations

import pytest

from cn_equity_strategies.research import momentum_stock_universe as universe


def test_resolve_momentum_stock_universe_csi500(monkeypatch: pytest.MonkeyPatch):
    def fake_fetch(index_code: str) -> tuple[str, ...]:
        assert index_code == universe.CSI500_INDEX_CODE
        return ("600519", "000001")

    monkeypatch.setattr(universe, "fetch_index_constituents", fake_fetch)
    assert universe.resolve_momentum_stock_universe("csi500") == ("600519", "000001")


def test_resolve_momentum_stock_universe_liquid_top(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(universe, "fetch_liquid_top_symbols", lambda top_n=300: ("600519",) * 60)
    result = universe.resolve_momentum_stock_universe("liquid_top", liquid_top_n=300)
    assert len(result) == 60


def test_momentum_cross_section_presets_declare_universe_mode():
    from cn_equity_strategies.strategies.industry_etf_rotation_presets import (
        STOCK_MOMENTUM_CROSS_SECTION_PRESETS,
    )

    default = STOCK_MOMENTUM_CROSS_SECTION_PRESETS["momentum_csi500_top5_vol20_monthly"]
    assert default["universe_mode"] == "csi500"
    assert default["top_n"] == 5
    assert default["sentiment_mode"] == "off"
