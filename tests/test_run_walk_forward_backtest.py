from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(QPK_SRC) not in sys.path:
    sys.path.insert(0, str(QPK_SRC))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.run_walk_forward_backtest as walk_forward
import cn_equity_strategies.backtest.orchestrator_runner as orchestrator_runner
from scripts.run_walk_forward_backtest import DEFAULT_WINDOWS, _baseline_param_set_id, _shared_market_history, run_walk_forward
from cn_equity_strategies.backtest.proxy_profile_registry import PROXY_PROFILE_REGISTRY


def test_run_walk_forward_persists_independent_lifecycle_baseline(tmp_path: Path) -> None:
    payload = run_walk_forward(
        profile="cn_index_etf_tactical_rotation",
        synthetic_days=900,
        store_root=tmp_path,
    )

    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "backtest" / "cn_equity" / "cn_index_etf_tactical_rotation").glob("*.json")
    ]

    assert payload["baseline"]["sharpe_ratio"] is not None
    baseline_records = [record for record in records if "_baseline_" in record["param_set_id"]]
    assert baseline_records
    assert all(record["params"] == {"min_history_days": 220} for record in baseline_records)
    assert not any(record["param_set_id"] == "cn_index_etf_tactical_rotation_full_compare" for record in records)
    assert not any("_wf" in record["param_set_id"] for record in records)
    assert payload["orchestrator_full_window"]["sharpe_ratio"] is not None
    assert payload["walk_forward_folds"]
    assert payload["compare"]["within_tolerance"] is True


def test_baseline_param_set_id_tracks_synthetic_days() -> None:
    first = _baseline_param_set_id(
        "cn_index_etf_tactical_rotation",
        {"min_history_days": 220},
        synthetic_days=900,
    )
    second = _baseline_param_set_id(
        "cn_index_etf_tactical_rotation",
        {"min_history_days": 220},
        synthetic_days=1200,
    )

    assert first != second


def test_run_walk_forward_does_not_persist_partial_results_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(BacktestOrchestrator, "walk_forward", _raise)
    with pytest.raises(RuntimeError, match="boom"):
        run_walk_forward(
            profile="cn_index_etf_tactical_rotation",
            synthetic_days=900,
            store_root=tmp_path,
        )
    assert not list(tmp_path.rglob("*.json"))


def test_run_walk_forward_does_not_persist_baseline_when_compare_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator

    original_run = BacktestOrchestrator.run

    def _mismatch(self, *args, **kwargs):
        result = original_run(self, *args, **kwargs)
        return replace(result, sharpe_ratio=float(result.sharpe_ratio or 0.0) + 1.0)

    monkeypatch.setattr(BacktestOrchestrator, "run", _mismatch)
    with pytest.raises(RuntimeError, match="baseline comparison failed"):
        run_walk_forward(
            profile="cn_index_etf_tactical_rotation",
            synthetic_days=900,
            compare_tolerance=0.0,
            store_root=tmp_path,
        )

    assert not list(tmp_path.rglob("*.json"))


def test_run_walk_forward_keeps_local_default_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(walk_forward, "DEFAULT_STORE_ROOT", tmp_path)

    run_walk_forward(profile="cn_index_etf_tactical_rotation", synthetic_days=900)

    assert list(tmp_path.rglob("*.json"))


def test_run_walk_forward_uses_external_history_and_writes_return_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = "cn_index_etf_tactical_rotation"
    dates = pd.bdate_range("2022-01-03", "2024-12-31")
    rows = []
    for symbol_index, symbol in enumerate(PROXY_PROFILE_REGISTRY[profile].extract_managed_symbols()):
        for day_index, day in enumerate(dates):
            rows.append(
                {
                    "as_of": day,
                    "symbol": symbol,
                    "close": 10.0 + symbol_index + day_index * (0.01 + symbol_index / 10000),
                }
            )
    history = pd.DataFrame(rows)
    monkeypatch.setattr(
        orchestrator_runner,
        "_synthetic_market_history",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("synthetic history must not be used")),
    )
    returns_output = tmp_path / "returns" / "portfolio_and_tracker_returns.csv"

    payload = run_walk_forward(
        profile=profile,
        windows=(
            (pd.Timestamp("2024-01-01").date(), pd.Timestamp("2024-06-30").date()),
            (pd.Timestamp("2024-07-01").date(), pd.Timestamp("2024-12-31").date()),
        ),
        store_root=tmp_path / "store",
        market_history=history,
        returns_output=returns_output,
    )

    return_matrix = pd.read_csv(returns_output)
    assert payload["baseline"]["end_date"] == "2024-12-31"
    assert payload["baseline"]["observation_count"] == 126
    assert {"as_of", profile, "buy_hold_510300"} <= set(return_matrix.columns)
    assert return_matrix[profile].notna().any()
    assert len(return_matrix) > payload["baseline"]["observation_count"]


def test_shared_market_history_rejects_stale_symbol_tail() -> None:
    profile = "cn_index_etf_tactical_rotation"
    dates = pd.bdate_range("2022-01-03", "2026-03-31")
    rows = [
        {"date": day, "symbol": symbol, "close": 10.0}
        for symbol in PROXY_PROFILE_REGISTRY[profile].extract_managed_symbols()
        for day in dates
        if not (symbol == "510500" and day > pd.Timestamp("2026-01-31"))
    ]

    with pytest.raises(ValueError, match="incomplete symbol coverage: 510500"):
        _shared_market_history(
            profile,
            {"min_history_days": 220},
            DEFAULT_WINDOWS,
            pd.DataFrame(rows),
        )
