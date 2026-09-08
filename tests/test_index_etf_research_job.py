from datetime import date
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest
from quant_platform_kit.common.cn_equity_calendar import is_cn_equity_trading_day
from quant_platform_kit.strategy_lifecycle.contracts import DriftResult, DriftStatus
from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore

from cn_equity_strategies.backtest.index_etf_research_job import PROFILE, make_index_etf_optimizer


def ResearchPromotionBudget(max_search_iterations=25, max_param_keys=4):
    return SimpleNamespace(max_search_iterations=max_search_iterations, max_param_keys=max_param_keys)


def history():
    days = [day for day in pd.date_range("2024-01-01", "2026-12-31") if is_cn_equity_trading_day(day.date())]
    return pd.DataFrame([
        {"date": day, "symbol": symbol, "close": 10 * (1.0003 + n * 0.0002) ** i * (1 + (i % 7) * 0.001)}
        for n, symbol in enumerate(("510300", "510500")) for i, day in enumerate(days)
    ])


def bind(tmp_path, frame, records):
    return make_index_etf_optimizer(
        market_history=frame, development_start=date(2025, 1, 2), development_end=date(2025, 12, 31),
        store=PerformanceStore(local_root=tmp_path), trial_records=records,
    )


def drift():
    return DriftResult(strategy_profile=PROFILE, domain="cn_equity", as_of=date(2026, 1, 5),
                       drift_score=0.8, status=DriftStatus.CRITICAL)


def test_runner_retains_actual_trading_day_warmup():
    from cn_equity_strategies.backtest.orchestrator_runner import _slice_history

    frame = _slice_history(
        history(), start_date=date(2025, 1, 2), end_date=date(2025, 12, 31), lookback_days=225,
    )
    prior_days = frame.loc[frame["date"] < "2025-01-02", "date"].nunique()
    assert prior_days == 225
    assert frame["date"].max().date() == date(2025, 12, 31)


def test_no_implicit_synthetic_input(tmp_path):
    with pytest.raises(ValueError, match="market_history_required"):
        bind(tmp_path, None, [])
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("outside", ["warmup", "development_end"])
def test_calendar_outside_pinned_coverage_is_rejected(tmp_path, outside):
    frame = history()
    if outside == "warmup":
        frame["date"] -= pd.DateOffset(years=1)
    with pytest.raises(ValueError, match="calendar_out_of_coverage"):
        make_index_etf_optimizer(
            market_history=frame, development_start=date(2025, 1, 2),
            development_end=date(2027, 1, 4) if outside == "development_end" else date(2025, 12, 31),
            store=PerformanceStore(local_root=tmp_path), trial_records=[],
        )
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("kind", ["missing_symbol", "nan", "nullable", "bool", "duplicate", "missing_day", "short"])
def test_bad_inputs_fail_before_backtest(tmp_path, kind):
    frame = history()
    if kind == "missing_symbol":
        frame = frame.loc[frame["symbol"] == "510300"]
    elif kind == "nan":
        frame.loc[0, "close"] = float("nan")
    elif kind == "nullable":
        frame["close"] = frame["close"].astype("Float64")
        frame.loc[0, "close"] = pd.NA
    elif kind == "bool":
        frame["close"] = frame["close"].astype(object)
        frame.loc[0, "close"] = True
    elif kind == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif kind == "missing_day":
        frame = frame.drop(index=50)
    else:
        frame = frame.loc[frame["date"] >= "2025-01-01"]
    with pytest.raises(ValueError):
        bind(tmp_path, frame, [])
    assert not list(tmp_path.rglob("*.json"))


def test_real_optimizer_calculates_and_persists_proxy_results(tmp_path):
    records = []
    optimize = bind(tmp_path, history(), records)
    proposal = optimize(drift(), ResearchPromotionBudget(max_search_iterations=2))
    assert proposal.current_metrics.observation_count > 100
    assert records[0]["params"]["universe_symbols"] == ("510300", "510500")
    assert records[0]["params"]["defensive_symbols"] == ()
    assert proposal.search_iterations == 2
    assert len(proposal.proposed_params) == 3
    assert proposal.walk_forward_passed is False
    assert len(records) >= 3  # baseline, bounded grid, possibly development segments
    assert all(item["status"] == "completed" for item in records)
    assert list(tmp_path.rglob("*.json"))


def test_future_prices_cannot_change_development_result(tmp_path):
    frame = history()
    first = bind(tmp_path / "first", frame, [])(drift(), ResearchPromotionBudget(max_search_iterations=1))
    frame.loc[frame["date"] > "2025-12-31", "close"] *= 1000
    second = bind(tmp_path / "second", frame, [])(drift(), ResearchPromotionBudget(max_search_iterations=1))
    assert first.current_metrics.total_return == second.current_metrics.total_return
    assert first.proposed_metrics.total_return == second.proposed_metrics.total_return
    assert first.proposed_params == second.proposed_params


def test_proxy_search_never_reaches_shadow_or_human_candidate(tmp_path):
    cycle_module = pytest.importorskip("quant_platform_kit.strategy_lifecycle.research_promotion_cycle")
    optimize = bind(tmp_path, history(), [])
    calls = []
    ticket = cycle_module.run_research_promotion_cycle(
        drift(), optimize=optimize, budget=cycle_module.ResearchPromotionBudget(max_search_iterations=1),
        enforce_backtest_gates=lambda proposal: None,
        record_shadow=lambda proposal: calls.append("shadow"),
        sync_console=lambda ticket: calls.append("console"),
    )
    assert ticket.state.value == "parked"
    assert ticket.live_authority_granted is False
    assert calls == []


def test_proxy_result_cannot_supply_strict_backtest_evidence(tmp_path):
    cycle_module = pytest.importorskip("quant_platform_kit.strategy_lifecycle.research_promotion_cycle")
    optimize = bind(tmp_path, history(), [])
    calls = []

    def proposal_for_gate(drift, budget):
        # Exercise the candidate branch with synthetic test evidence, never a PASS summary.
        return replace(optimize(drift, budget), recommendation="research_candidate")

    def strict_gate(proposal):
        calls.append("strict_gate")
        return None

    ticket = cycle_module.run_research_promotion_cycle(
        drift(), optimize=proposal_for_gate, enforce_backtest_gates=strict_gate,
        budget=cycle_module.ResearchPromotionBudget(max_search_iterations=1),
        record_shadow=lambda proposal: calls.append("shadow"),
        sync_console=lambda ticket: calls.append("console"),
    )
    assert ticket.state.value == "parked"
    assert "missing_promotion_backtest_evidence" in ticket.notes
    assert calls == ["strict_gate"]


def test_failed_trial_is_retained_without_exception_detail(tmp_path, monkeypatch):
    import cn_equity_strategies.backtest.orchestrator_runner as runner_module

    records = []
    optimize = bind(tmp_path, history(), records)

    def fail(*args, **kwargs):
        raise RuntimeError("untrusted provider detail")

    monkeypatch.setattr(runner_module, "run_proxy_backtest", fail)
    with pytest.raises(RuntimeError):
        optimize(drift(), ResearchPromotionBudget(max_search_iterations=1))
    assert len(records) == 1
    assert records[0]["status"] == "failed"
    assert records[0]["reason"] == "backtest_failed"
    assert "untrusted" not in str(records)


def test_missing_cli_inputs_park_without_loading_market_data(monkeypatch):
    from scripts.run_cn_index_etf_walk_forward_pilot import run_bounded_research

    def must_not_load(*args, **kwargs):
        pytest.fail("missing input must not load market data")

    monkeypatch.setattr(pd, "read_csv", must_not_load)
    payload = run_bounded_research(SimpleNamespace())
    assert payload["status"] == "parked"
    assert payload["reason"] == "research_inputs_missing"
    assert payload["trials"] == []
    assert payload["no_order"] is True
    assert payload["promotion_eligible"] is False


def test_cli_executes_all_twelve_candidates_as_learning_only(tmp_path):
    from scripts.run_cn_index_etf_walk_forward_pilot import run_bounded_research

    market_path = tmp_path / "synthetic.csv"
    history().to_csv(market_path, index=False)
    payload = run_bounded_research(SimpleNamespace(
        market_history=market_path, development_start=date(2025, 1, 2), development_end=date(2025, 12, 31),
        store_root=tmp_path / "isolated-store",
    ))
    assert payload["status"] == "learning_completed"
    assert payload["proposal"]["search_iterations"] == 12
    assert 13 <= len(payload["trials"]) <= 16
    assert payload["reason"] == "strict_promotion_evidence_missing"
    assert payload["input_provenance"] == "caller_supplied_unverified"
    assert payload["learning_only"] is True
    assert payload["promotion_eligible"] is False
    assert payload["live_ready"] is False
    assert payload["no_order"] is True


def test_wrong_candidate_and_low_budget_do_not_start_trials(tmp_path):
    records = []
    optimize = bind(tmp_path, history(), records)
    with pytest.raises(ValueError, match="identity_mismatch"):
        optimize(replace(drift(), strategy_profile="other"), ResearchPromotionBudget())
    with pytest.raises(ValueError, match="budget_insufficient"):
        optimize(drift(), ResearchPromotionBudget(max_param_keys=2))
    assert records == []
