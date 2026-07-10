from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(QPK_SRC) not in sys.path:
    sys.path.insert(0, str(QPK_SRC))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scripts.run_walk_forward_backtest as walk_forward
from scripts.run_walk_forward_backtest import _baseline_param_set_id, run_walk_forward


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
