"""Synthetic hand calculations only; these fixtures are not market evidence."""

from datetime import date
from hashlib import sha256
import json

import pandas as pd
import pytest
from quant_platform_kit.data.research_input import canonical_research_input_manifest_bytes
from quant_platform_kit.strategy_lifecycle.contracts import PromotionCostModel

from cn_equity_strategies.backtest.index_etf_strict_runner import (
    CnIndexEtfBacktestRunner, IndexEtfExecutionConfig, load_index_etf_input,
)


def package(days=None, *, mutate=None, events=None, synthetic=True):
    days = list(days or pd.bdate_range("2024-01-02", periods=230).strftime("%Y-%m-%d"))
    rows = [dict(date=day, symbol=symbol, open=10.0, high=11.0, low=9.0, close=10.0,
                 volume=100000, suspended=False, limit_up=11.0, limit_down=9.0,
                 status_known_at=day + "T09:00:00+08:00", available_at=day + "T15:01:00+08:00")
            for day in days for symbol in ("510300", "510500")]
    if mutate:
        mutate(rows)
    license_bytes = b"Synthetic test license fixture, never used as a real permission."
    documents = {
        "normalized/daily.json": rows,
        "calendar/sessions.json": {"start_date": days[0], "end_date": days[-1], "sessions": days},
        "corporate_actions/events.json": {"complete_from": days[0], "complete_through": days[-1], "events": events or []},
        "evidence/license_identity.json": {"source_identity": "official:synthetic-fixture", "revision": "test-v1",
                                           "retention_scope": "private-retention-permitted", "content_sha256": sha256(license_bytes).hexdigest()},
    }
    members = {name: json.dumps(value, separators=(",", ":"), allow_nan=False).encode() for name, value in documents.items()}
    members["evidence/license.bin"] = license_bytes
    manifest = dict(
        schema_version="research_input_manifest.v1", manifest_id="synthetic-test",
        research_input_contract_id="qsl.cn_index_etf.execution_input.v1", domain="cn_equity",
        profile="cn_index_etf_tactical_rotation",
        artifact_type="cn_index_etf_synthetic_execution_history" if synthetic else "cn_index_etf_execution_history",
        observed_at="2026-09-08T00:00:00Z", effective_at=days[-1]+"T15:01:00+08:00", as_of="2026-09-08T00:00:00Z",
        producer={"repository": "QuantStrategyLab/CnEquitySnapshotPipelines", "commit_sha": "a"*40,
                  "tree_sha": "b"*40, "tool": "synthetic.fixture", "tool_version": "1"},
        calendar={"calendar_id": "SSE", "timezone": "Asia/Shanghai", "session_date": days[-1],
                  "source": "official:synthetic-fixture", "source_revision": "sha256:"+sha256(members["calendar/sessions.json"]).hexdigest()},
        adjustment={"policy": "raw", "source": "official:synthetic-fixture", "source_revision": "test-v1"},
        sources=[{"source_id": "synthetic-fixture", "revision": "test-v1", "observed_at": "2026-09-08T00:00:00Z",
                  "content_sha256": sha256(members["normalized/daily.json"]).hexdigest()}],
        members=[{"path": path, "media_type": "application/json" if path.endswith(".json") else "text/plain",
                  "size_bytes": len(content), "sha256": sha256(content).hexdigest()} for path, content in sorted(members.items())],
    )
    encoded = canonical_research_input_manifest_bytes(manifest)
    return encoded, members, sha256(encoded).hexdigest()


def inputs(*args, **kwargs):
    manifest, members, digest = package(*args, **kwargs)
    return load_index_etf_input(manifest, members, expected_manifest_sha256=digest)


def run_targets(data, targets, *, initial_cash=10005.0, participation=1.0):
    runner = CnIndexEtfBacktestRunner(
        data, config=IndexEtfExecutionConfig(initial_cash=initial_cash, cash_reserve_ratio=0,
                                            max_previous_volume_participation=participation),
    )
    dates = data.sessions
    return runner.simulate_targets(targets, start_date=dates[1], end_date=dates[-1],
                                   cost_model=PromotionCostModel("test", 0, 0))


def test_no_input_or_manifest_substitution():
    manifest, members, digest = package()
    with pytest.raises(ValueError, match="manifest_identity"):
        load_index_etf_input(manifest, members, expected_manifest_sha256="0"*64)
    members["normalized/daily.json"] += b" "
    with pytest.raises(ValueError, match="member_identity"):
        load_index_etf_input(manifest, members, expected_manifest_sha256=digest)


@pytest.mark.parametrize("kind", ["bool_price", "missing_symbol", "duplicate", "status_future", "status_after_open", "close_future", "daily_gap", "negative_volume"])
def test_invalid_history_rejected_before_execution(kind):
    def change(rows):
        if kind == "bool_price": rows[0]["open"] = True
        elif kind == "missing_symbol": rows[:] = [r for r in rows if r["symbol"] != "510500"]
        elif kind == "duplicate": rows.append(rows[0])
        elif kind == "status_future": rows[0]["status_known_at"] = rows[0]["date"]+"T15:00:00+08:00"
        elif kind == "status_after_open": rows[0]["status_known_at"] = rows[0]["date"]+"T09:26:00+08:00"
        elif kind == "close_future": rows[0]["available_at"] = rows[0]["date"]+"T14:59:00+08:00"
        elif kind == "daily_gap": rows.pop(0)
        else: rows[0]["volume"] = -1
    with pytest.raises(ValueError):
        inputs(mutate=change)


def test_buy_cash_round_trip_includes_both_fees_and_initial_loss():
    data = inputs(["2024-01-02", "2024-01-03", "2024-01-04"])
    result = run_targets(data, {date(2024,1,2): {"510300": 1.0}, date(2024,1,3): {}})
    assert result.final_cash == 9995.0
    assert result.final_holdings == {}
    assert [t["quantity"] for t in result.trades] == [1000, 1000]
    assert result.total_fees == 10.0
    assert result.daily_returns.iloc[0] == pytest.approx(10000/10005-1)
    assert result.metrics["max_drawdown"] == pytest.approx(9995/10005-1)


def test_open_fill_never_uses_current_close_or_volume_for_sizing():
    days=["2024-01-02", "2024-01-03", "2024-01-04"]
    def change(rows):
        for row in rows:
            if row["date"] == days[1]:
                row["open"]=10.5; row["close"]=11.0; row["volume"]=100000000
    data=inputs(days, mutate=change)
    result=run_targets(data,{date(2024,1,2):{"510300":1.0}},participation=.005)
    assert result.trades[0]["quantity"] == 500  # previous 100000 shares only
    assert result.trades[0]["price"] == 10.5
    assert result.trades[0]["signal_date"] == date(2024,1,2)
    assert result.trades[0]["execution_date"] == date(2024,1,3)
    assert result.final_cash == 4750.0


@pytest.mark.parametrize("kind",["suspended","limit_up","limit_down"])
def test_unfillable_orders_preserve_cash_and_shares(kind):
    days=["2024-01-02","2024-01-03","2024-01-04"]
    def change(rows):
        for row in rows:
            if row["date"] == (days[2] if kind=="limit_down" else days[1]) and row["symbol"]=="510300":
                if kind=="suspended": row["suspended"]=True;row["volume"]=0
                else: row["open"]=row[kind]
    result=run_targets(inputs(days,mutate=change),{date(2024,1,2):{"510300":1.0},date(2024,1,3):{}})
    assert any(order["reason"]==kind for order in result.unfilled)
    if kind=="limit_down": assert result.final_holdings=={"510300":1000}
    else: assert result.final_cash==10005;assert result.final_holdings=={}


def test_dividend_receivable_is_not_spendable_until_payment_and_split_preserves_nav():
    days=["2024-01-02","2024-01-03","2024-01-04","2024-01-05"]
    event=dict(symbol="510300",record_date=days[1],ex_date=days[2],pay_date=days[3],
               cash_per_share=1.0,split_ratio=2,known_at=days[1]+"T08:00:00+08:00")
    def change(rows):
        for row in rows:
            if row["date"]>=days[2] and row["symbol"]=="510300":
                row.update(open=4.5,close=4.5,high=4.95,low=4.05,limit_up=4.95,limit_down=4.05)
    data=inputs(days,mutate=change,events=[event])
    result=run_targets(data,{date(2024,1,2):{"510300":1.0}})
    assert result.final_holdings=={"510300":2000}
    assert result.ledger[1]["cash"]==0
    assert result.ledger[1]["receivables"]==1000
    assert result.ledger[1]["equity"]==10000
    assert result.final_cash==1000
    assert data.signal_history(date(2024,1,5)).query("symbol == '510300'")["close"].tolist()==[10,10,10,10]


def test_synthetic_input_is_not_promotion_capability():
    runner=CnIndexEtfBacktestRunner(inputs())
    assert runner.runner_kind=="synthetic"
    with pytest.raises(ValueError,match="promotion_identity"):
        runner.run_locked_oos("cn_index_etf_tactical_rotation",{},start_date=date(2024,1,2),end_date=date(2025,1,2),
                              cost_model=PromotionCostModel("test",3,5))


def test_historical_schema_is_not_a_source_approval():
    data=inputs(synthetic=False)
    assert CnIndexEtfBacktestRunner(data).runner_kind=="unverified"
    assert CnIndexEtfBacktestRunner(data,trusted_historical_manifest_sha256="0"*64).runner_kind=="unverified"
    synthetic=inputs()
    assert CnIndexEtfBacktestRunner(synthetic,trusted_historical_manifest_sha256=synthetic.manifest_sha256).runner_kind=="synthetic"


def test_no_free_rebalancing_between_monthly_orders():
    days=["2024-01-02","2024-01-03","2024-01-04"]
    def change(rows):
        for row in rows:
            if row["date"]==days[2]: row["open"]=row["close"]=11
    result=run_targets(inputs(days,mutate=change),{date(2024,1,2):{"510300":1}})
    assert len(result.trades)==1
    assert result.final_holdings=={"510300":1000}
    assert result.ledger[-1]["equity"]==11000


def test_open_gap_and_costs_cannot_overspend_cash():
    data=inputs(["2024-01-02","2024-01-03"],mutate=lambda rows: rows[2].update(open=10.9))
    runner=CnIndexEtfBacktestRunner(data,config=IndexEtfExecutionConfig(initial_cash=10005.,cash_reserve_ratio=0.,max_previous_volume_participation=1.))
    result=runner.simulate_targets({date(2024,1,2):{"510300":1.}},start_date=date(2024,1,3),end_date=date(2024,1,3),
                                   cost_model=PromotionCostModel("stress",30,5,5))
    assert result.final_holdings=={"510300":900}
    assert result.trades[0]["price"]==10.911
    assert result.final_cash>=0
    assert result.final_cash+900*10.911+result.total_fees==pytest.approx(10005.)


def test_strict_search_refuses_holdout_rows(tmp_path):
    from cn_equity_strategies.backtest.index_etf_research_job import make_strict_index_etf_optimizer
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore
    with pytest.raises(ValueError,match="strict_development_partition_required"):
        make_strict_index_etf_optimizer(data=inputs(),development_start=date(2024,1,2),development_end=date(2024,6,1),
                                       store=PerformanceStore(local_root=tmp_path),trial_records=[])


def test_actual_strategy_runs_with_causal_adjusted_signals(tmp_path):
    from cn_equity_strategies.backtest.index_etf_research_job import BASELINE_PARAMS
    days=list(pd.bdate_range("2024-01-02",periods=230).strftime("%Y-%m-%d"))
    def change(rows):
        for row in rows:
            close=10+days.index(row["date"])*.01
            row.update(open=close,close=close,high=close*1.02,low=close*.98,limit_up=close*1.1,limit_down=close*.9)
    runner=CnIndexEtfBacktestRunner(inputs(days,mutate=change),development_end=date.fromisoformat(days[-1]))
    result=runner.run("cn_index_etf_tactical_rotation",BASELINE_PARAMS,date.fromisoformat(days[220]),date.fromisoformat(days[-1]))
    assert result.observation_count==10
    assert len(runner.last_simulation.trades)>0
    assert result.benchmark_symbol=="510300"
    assert result.validation_identity is None
    with pytest.raises(ValueError,match="development_boundary"):
        runner.run("cn_index_etf_tactical_rotation",BASELINE_PARAMS,date.fromisoformat(days[220]),date(2025,1,1))


def test_existing_qpk_promotion_protocol_computes_every_fold_and_oos(tmp_path):
    # Even this historical-schema stand-in is generated synthetic test data.
    from types import SimpleNamespace
    from quant_platform_kit.strategy_lifecycle.contracts import PurgedWalkForwardFold
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore
    from cn_equity_strategies.backtest.index_etf_research_job import BASELINE_PARAMS, make_index_etf_promotion_gate
    days=list(pd.bdate_range("2020-01-02","2025-01-08").strftime("%Y-%m-%d"))
    data=inputs(days,synthetic=False)
    folds=tuple(PurgedWalkForwardFold(date(y,1,4),date(y,11,15),date(y,11,19),date(y,12,31)) for y in [2021,2022,2023])
    gate=make_index_etf_promotion_gate(data=data,development_end=date(2021,1,1),folds=folds,
                                     locked_oos_start=date(2024,1,8),locked_oos_end=date(2025,1,8),
                                     purge_days=1,embargo_days=1,source_revision="c"*40,
                                     store=PerformanceStore(local_root=tmp_path),config=IndexEtfExecutionConfig(),
                                     trusted_historical_manifest_sha256=data.manifest_sha256,
                                     cost_model=PromotionCostModel("synthetic-test-cost",3.,5.))
    result=gate(SimpleNamespace(strategy_profile="cn_index_etf_tactical_rotation",domain="cn_equity",proposed_params=BASELINE_PARAMS))
    assert len(result.fold_results)==3
    assert all(item.observation_count>0 for item in result.fold_results)
    assert result.locked_oos_result.observation_count>250
    assert result.locked_oos_result.validation_identity.fold_role=="locked_oos"
    assert all(item.total_return==0 for item in result.fold_results)  # flat input -> cash, never fabricated scores


def test_validated_input_cannot_be_mutated_after_root_check():
    data = inputs()
    with pytest.raises(TypeError):
        data._rows[0]["close"] = 999.


def test_fold_requires_warmup_inside_its_training_partition():
    from quant_platform_kit.strategy_lifecycle.contracts import PurgedWalkForwardFold
    from cn_equity_strategies.backtest.index_etf_research_job import BASELINE_PARAMS
    data = inputs(pd.bdate_range("2020-01-02", "2025-01-08").strftime("%Y-%m-%d").tolist(), synthetic=False)
    folds = tuple(PurgedWalkForwardFold(date(y, 1, 4), date(y, 3, 1), date(y, 3, 5), date(y, 12, 31)) for y in [2021, 2022, 2023])
    runner = CnIndexEtfBacktestRunner(data, development_end=date(2021, 1, 1), selected_params=BASELINE_PARAMS,
                                    folds=folds, locked_oos=(date(2024, 1, 8), date(2025, 1, 8)),
                                    trusted_historical_manifest_sha256=data.manifest_sha256)
    with pytest.raises(ValueError, match="fold_training_warmup_incomplete"):
        runner.run_purged_fold("cn_index_etf_tactical_rotation", BASELINE_PARAMS, fold=folds[0],
                               purge_days=1, embargo_days=1, cost_model=PromotionCostModel("test", 3., 5.))


def test_strict_cli_missing_package_does_not_fall_back_to_proxy(tmp_path):
    from types import SimpleNamespace
    from scripts.run_cn_index_etf_walk_forward_pilot import run_bounded_research
    result = run_bounded_research(SimpleNamespace(strict_input_package=tmp_path, expected_manifest_sha256="a" * 64,
                                                 development_start=date(2024, 1, 1), development_end=date(2024, 12, 31),
                                                 store_root=tmp_path / "store"))
    assert result["reason"] == "strict_input_or_backtest_failed"
    assert result["execution_model"] == "next_open_daily_v1"
    assert result["no_order"] is True


def test_strict_cli_computes_synthetic_development_only(tmp_path):
    from types import SimpleNamespace
    from scripts.run_cn_index_etf_walk_forward_pilot import run_bounded_research
    manifest, members, digest = package()
    root = tmp_path / "input"
    root.mkdir()
    (root / "research_input_manifest.v1.json").write_bytes(manifest)
    for name, content in members.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    result = run_bounded_research(SimpleNamespace(strict_input_package=root, expected_manifest_sha256=digest,
                                                 development_start=date(2024, 11, 5), development_end=date(2024, 11, 18),
                                                 store_root=tmp_path / "store"))
    assert result["status"] == "learning_completed"
    assert result["execution_model"] == "next_open_daily_v1"
    assert result["input_provenance"] == "synthetic"
    assert result["promotion_eligible"] is False
    assert result["live_ready"] is False
    assert len(result["trials"]) == 13  # baseline + 12 grid; short development has no segment runs
    assert all(t["status"] == "completed" for t in result["trials"])


def test_job_identity_binds_inputs_plan_parameters_and_all_cost_settings(tmp_path, monkeypatch):
    from dataclasses import replace
    from cn_equity_strategies.backtest.index_etf_research_job import index_etf_research_identity
    config = IndexEtfExecutionConfig()
    kwargs = dict(development_input=inputs(), validation_input=inputs(), code_revision="c" * 40,
                  development_start=date(2024, 11, 5), development_end=date(2024, 11, 18), folds=(),
                  locked_oos_start=date(2025, 1, 1), locked_oos_end=date(2026, 1, 1), purge_days=1, embargo_days=1,
                  config=config, cost_model=PromotionCostModel("test", 3., 5.))
    identity = index_etf_research_identity(**kwargs)
    assert set(identity) == {"code_revision", "input_revision", "param_space_revision", "cost_model_revision", "validator_revision"}
    for field_name, value in [("minimum_commission", 6.), ("cash_reserve_ratio", .03), ("max_previous_volume_participation", .005), ("initial_cash", 500000.)]:
        other = index_etf_research_identity(**{**kwargs, "config": replace(config, **{field_name: value})})
        assert other["cost_model_revision"] != identity["cost_model_revision"]
    other = index_etf_research_identity(**{**kwargs, "cost_model": PromotionCostModel("test", 3., 6.)})
    assert other["cost_model_revision"] != identity["cost_model_revision"]
    other = index_etf_research_identity(**{**kwargs, "purge_days": 2})
    assert other["input_revision"] != identity["input_revision"]
    from cn_equity_strategies.strategies import etf_rotation_core
    changed_core = tmp_path / "etf_rotation_core.py"
    from pathlib import Path
    changed_core.write_bytes(Path(etf_rotation_core.__file__).read_bytes() + b"\n# changed test core\n")
    monkeypatch.setattr(etf_rotation_core, "__file__", str(changed_core))
    assert index_etf_research_identity(**kwargs)["code_revision"] != identity["code_revision"]


def test_full_job_refuses_unapproved_or_synthetic_roots_before_any_callback(tmp_path):
    from cn_equity_strategies.backtest.index_etf_research_job import run_index_etf_research_job
    data = inputs()
    calls = []
    with pytest.raises(ValueError, match="approved_historical_inputs_required"):
        run_index_etf_research_job(development_input=data, validation_input=data,
                                  trusted_input_roots={"development": data.manifest_sha256, "validation": data.manifest_sha256},
                                  development_start=date(2024, 11, 5), development_end=date(2024, 11, 18), folds=(),
                                  locked_oos_start=date(2025, 1, 1), locked_oos_end=date(2026, 1, 1), purge_days=1, embargo_days=1,
                                  code_revision="c" * 40, ticket_dir=tmp_path / "tickets", store_root=tmp_path / "store",
                                  as_of=date(2026, 9, 9), drift_score=.8, source_revision="d" * 40,
                                  diagnose=lambda *_: calls.append("diagnose"), record_shadow=lambda *_: calls.append("shadow"),
                                  sync_console=lambda *_: calls.append("console"))
    assert calls == []
    assert not list(tmp_path.rglob("*.json"))


def test_benchmark_retries_monthly_target_under_same_volume_constraint():
    from cn_equity_strategies.backtest.index_etf_research_job import BASELINE_PARAMS
    days = list(pd.bdate_range("2024-01-02", periods=290).strftime("%Y-%m-%d"))
    def change(rows):
        for row in rows:
            close = 10 + days.index(row["date"]) * .01
            row.update(open=close, close=close, high=close*1.02, low=close*.98, limit_up=close*1.1, limit_down=close*.9,
                       volume=100 if row["date"] == days[219] else 10_000_000)
    runner = CnIndexEtfBacktestRunner(inputs(days, mutate=change), development_end=date.fromisoformat(days[-1]))
    result = runner.run("cn_index_etf_tactical_rotation", BASELINE_PARAMS, date.fromisoformat(days[220]), date.fromisoformat(days[-1]))
    assert result.benchmark_cagr > 0  # Initial order has zero capacity; later monthly decision can buy.


def test_real_cycle_adapter_persists_rejected_search_and_reuses_terminal_without_ai(tmp_path, monkeypatch):
    # Historical schema below remains a synthetic stand-in. No real market claim.
    from cn_equity_strategies.backtest.index_etf_research_job import run_index_etf_research_job
    from quant_platform_kit.strategy_lifecycle.contracts import PurgedWalkForwardFold
    development = inputs(pd.bdate_range("2019-01-02", "2020-12-31").strftime("%Y-%m-%d").tolist(), synthetic=False)
    validation = inputs(pd.bdate_range("2020-01-02", "2025-01-08").strftime("%Y-%m-%d").tolist(), synthetic=False)
    folds = tuple(PurgedWalkForwardFold(date(y, 1, 4), date(y, 11, 15), date(y, 11, 19), date(y, 12, 31)) for y in [2021, 2022, 2023])
    calls = []
    from quant_platform_kit.strategy_lifecycle import promotion_actionable_runner
    original_cycle = promotion_actionable_runner.run_actionable_research_promotion
    def pending_reader(*_):
        calls.append("read_pending_shadow")
        return {"status": "pending"}
    def checked_cycle(*, research_identity, admit_new_research, read_pending_shadow=None, **arguments):
        assert read_pending_shadow is pending_reader
        return original_cycle(research_identity=research_identity, admit_new_research=admit_new_research,
                              read_pending_shadow=read_pending_shadow, **arguments)
    monkeypatch.setattr(promotion_actionable_runner, "run_actionable_research_promotion", checked_cycle)
    def diagnosis(*_):
        calls.append("diagnose")
        return {"optimization_needed": True}
    def shadow(*_):
        calls.append("shadow")
        return {"evidence_kind": "missing", "passed": False}
    def admit(*_):
        calls.append("admit")
        return True
    kwargs = dict(development_input=development, validation_input=validation,
                  trusted_input_roots={"development": development.manifest_sha256, "validation": validation.manifest_sha256},
                  development_start=date(2020, 1, 2), development_end=date(2020, 12, 31), folds=folds,
                  locked_oos_start=date(2024, 1, 8), locked_oos_end=date(2025, 1, 8), purge_days=1, embargo_days=1,
                  code_revision="c" * 40, ticket_dir=tmp_path / "tickets", store_root=tmp_path / "store",
                  as_of=date(2026, 9, 9), evaluation_date=date(2026, 9, 9), drift_score=.8, source_revision="d" * 40,
                  diagnose=diagnosis, record_shadow=shadow, sync_console=lambda _: calls.append("console"), admit_new_research=admit,
                  read_pending_shadow=pending_reader)
    first = run_index_etf_research_job(**kwargs)
    assert first["status"] == "parked"
    assert calls == ["admit", "diagnose"]
    from pathlib import Path
    ticket = json.loads(Path(first["ticket_path"]).read_text())
    assert ticket["notes"] == ["recommendation=reject"]
    assert set(ticket["research_progress"]["stages"]) == {"diagnose", "optimize"}
    records = json.loads(Path(first["trial_records_path"]).read_text())
    assert len(records) == 13  # no improvement -> baseline + 12 grid, no development segments
    assert all(r["status"] == "completed" for r in records)
    second = run_index_etf_research_job(**kwargs)
    assert second["resumed"] is True
    assert second["research_key"] == first["research_key"]
    assert calls == ["admit", "diagnose"]
    assert second["no_order"] is True and second["live_ready"] is False
    old_root = Path(first["trial_records_path"]).parent
    before = {p: p.read_bytes() for p in old_root.rglob("*.json")}
    third = run_index_etf_research_job(**{**kwargs, "as_of": date(2026, 9, 8), "source_revision": "e" * 40})
    assert third["research_key"] != first["research_key"]
    assert third["trial_records_path"] != first["trial_records_path"]
    assert all(p.read_bytes() == content for p, content in before.items())
    assert calls == ["admit", "diagnose", "admit", "diagnose"]


def test_malformed_license_record_has_fixed_failure_reason():
    manifest, members, _ = package()
    members["evidence/license_identity.json"] = b"[]"
    decoded = json.loads(manifest)
    member = next(item for item in decoded["members"] if item["path"] == "evidence/license_identity.json")
    member.update(size_bytes=2, sha256=sha256(b"[]").hexdigest())
    encoded = canonical_research_input_manifest_bytes(decoded)
    with pytest.raises(ValueError, match="^cn_execution_license_evidence_invalid$"):
        load_index_etf_input(encoded, members, expected_manifest_sha256=sha256(encoded).hexdigest())
