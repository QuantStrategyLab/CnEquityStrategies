"""Bounded development search for the existing index ETF profile.

This is an optimize callback for QPK's research cycle, not a second lifecycle.
The caller supplies an approved, frozen development input. Close-only proxy
results remain learning evidence and cannot supply promotion/shadow evidence.
"""

from __future__ import annotations

from collections.abc import MutableSequence
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from quant_platform_kit.common.cn_equity_calendar import is_cn_equity_trading_day
from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
from quant_platform_kit.strategy_lifecycle.contracts import ParamDimension, ParamSearchSpace
from quant_platform_kit.strategy_lifecycle.param_optimizer import run_grid_search

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner
from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig

PROFILE = "cn_index_etf_tactical_rotation"
SYMBOLS = ("510300", "510500")
BASELINE_PARAMS = {"momentum_window_days": 60, "trend_window_days": 200, "top_n": 1}
SEARCH_SPACE = ParamSearchSpace(
    strategy_profile=PROFILE,
    domain="cn_equity",
    dimensions={
        "momentum_window_days": ParamDimension(
            name="momentum_window_days", param_type="int", bounds=(40, 80), step=20, current_value=60,
        ),
        "trend_window_days": ParamDimension(
            name="trend_window_days", param_type="int", bounds=(120, 200), step=80, current_value=200,
        ),
        "top_n": ParamDimension(name="top_n", param_type="int", bounds=(1, 2), step=1, current_value=1),
    },
)
FIXED_STRATEGY_PARAMS = {
    "universe_symbols": SYMBOLS,
    "defensive_symbols": (),
    "benchmark_symbol": "510300",
    "benchmark_trend_window_days": 200,
    "volatility_window_days": 63,
    "min_history_days": 220,
    "weighting_mode": "equal",
    "target_annual_volatility": None,
    "max_gross_exposure": 1.0,
    "max_pair_correlation": 1.0,
}
PROXY_LIMITATIONS = (
    "close_only_execution_proxy",
    "slippage_and_liquidity_not_validated",
    "corporate_actions_and_tradability_not_validated",
    "strict_purged_wfa_and_locked_oos_missing",
    "paired_forward_shadow_missing",
)


def make_index_etf_optimizer(
    *,
    market_history: pd.DataFrame | None,
    development_start: date,
    development_end: date,
    store: Any,
    trial_records: MutableSequence[dict[str, Any]],
):
    """Bind an explicit input/window to ``optimize(drift, budget)``.

    No provider, model, synthetic fallback, shadow, runtime or console call is
    made here. The owning job must persist ``trial_records`` even on failure.
    QPK persists successful BacktestResults in the supplied isolated store.
    """
    if market_history is None or market_history.empty:
        raise ValueError("market_history_required")
    if type(development_start) is not date or type(development_end) is not date:
        raise ValueError("development_window_required")
    if development_start >= development_end:
        raise ValueError("development_window_invalid")
    if not {"date", "symbol", "close"}.issubset(market_history.columns):
        raise ValueError("market_history_columns_missing")
    frame = market_history[["date", "symbol", "close"]].copy(deep=True)
    try:
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    except (TypeError, ValueError):
        raise ValueError("market_history_invalid") from None
    if frame["date"].dt.tz is not None or frame["date"].isna().any():
        raise ValueError("market_history_requires_local_session_dates")
    # Exclude holdout rows before inspecting prices or invoking the optimizer.
    frame = frame.loc[frame["date"] <= pd.Timestamp(development_end)].sort_values(["date", "symbol"])
    if frame.empty or frame["date"].max() < pd.Timestamp(development_start):
        raise ValueError("development_history_missing")
    # The currently pinned simulator calendar explicitly covers 2024–2026.
    # Outside that range it falls back to weekdays; do not call that complete.
    if frame["date"].min() < pd.Timestamp("2024-01-01") or development_end > date(2026, 12, 31):
        raise ValueError("development_calendar_out_of_coverage")
    if frame["close"].map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("market_history_price_invalid")
    try:
        frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    except (TypeError, ValueError):
        raise ValueError("market_history_price_invalid") from None
    if set(frame["symbol"]) != set(SYMBOLS):
        raise ValueError("market_history_requires_frozen_etf_universe")
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("market_history_duplicate")
    if frame["close"].isna().any() or not np.isfinite(frame["close"]).all() or not frame["close"].gt(0).all():
        raise ValueError("market_history_price_invalid")
    expected_days = pd.DatetimeIndex(
        day for day in pd.date_range(frame["date"].min(), development_end)
        if is_cn_equity_trading_day(day.date())
    )
    if any(
        set(frame.loc[frame["symbol"] == symbol, "date"]) != set(expected_days)
        for symbol in SYMBOLS
    ):
        raise ValueError("development_calendar_coverage_incomplete")
    warmup = frame.loc[frame["date"] < pd.Timestamp(development_start)]
    if any(len(warmup.loc[warmup["symbol"] == symbol]) < 220 for symbol in SYMBOLS):
        raise ValueError("development_warmup_incomplete")

    class RecordedRunner(CnProxyBacktestRunner):
        def run(self, strategy_profile, params, start_date=None, end_date=None):
            record = {
                "params": {**FIXED_STRATEGY_PARAMS, **dict(params)},
                "status": "failed", "reason": "backtest_failed",
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            }
            trial_records.append(record)
            try:
                result = super().run(strategy_profile, params, start_date, end_date)
            except Exception:
                raise RuntimeError("cn_research_backtest_failed") from None
            record.update(status="completed", reason=None)
            return result

    runner = RecordedRunner(
        market_history=frame,
        strategy_defaults=FIXED_STRATEGY_PARAMS,
        config=ProxyBacktestConfig(rebalance_frequency="monthly", min_history_days=220),
    )
    orchestrator = BacktestOrchestrator(store=store)
    orchestrator.register_runner("cn_equity", runner)

    def optimize(drift, budget):
        if drift.strategy_profile != PROFILE or drift.domain != "cn_equity":
            raise ValueError("research_candidate_identity_mismatch")
        if budget.max_param_keys < len(BASELINE_PARAMS) or budget.max_search_iterations < 1:
            raise ValueError("research_budget_insufficient")
        proposal = run_grid_search(
            PROFILE,
            domain="cn_equity",
            orchestrator=orchestrator,
            search_space=SEARCH_SPACE,
            current_params=BASELINE_PARAMS,
            start_date=development_start,
            end_date=development_end,
            max_combinations=min(12, budget.max_search_iterations),
        )
        store.save_proposal(proposal)
        return proposal

    return optimize


def make_strict_index_etf_optimizer(
    *, data, development_start: date, development_end: date, store,
    trial_records: MutableSequence[dict[str, Any]], config=None, cost_model=None, trial_path=None,
):
    """Development-only search using the explicit next-open execution model.

    The producer must provide a separate development package. Holdout rows
    cannot be passed to this factory, even when a caller promises not to use them.
    The resulting proposal is still research, never promotion or live authority.
    """
    from cn_equity_strategies.backtest.index_etf_strict_runner import CnIndexEtfBacktestRunner, IndexEtfInput

    if (not isinstance(data, IndexEtfInput) or type(development_start) is not date
            or type(development_end) is not date or development_start >= development_end
            or data.sessions[-1] != development_end
            or not any(development_start <= day <= development_end for day in data.sessions)
            or sum(day < development_start for day in data.sessions) < 220):
        raise ValueError("strict_development_partition_required")
    runner = CnIndexEtfBacktestRunner(data, config=config, cost_model=cost_model, development_end=development_end)

    def persist_trials():
        if trial_path is not None:
            import json
            import os
            from pathlib import Path
            path = Path(trial_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            with temporary.open("w") as stream:
                json.dump(list(trial_records), stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)

    class RecordedRunner:
        def run(self, strategy_profile, params, start_date=None, end_date=None):
            record = {"params": dict(params), "start_date": start_date.isoformat() if start_date else None,
                      "end_date": end_date.isoformat() if end_date else None,
                      "status": "running", "reason": "outcome_unknown"}
            trial_records.append(record)
            persist_trials()
            try:
                result = runner.run(strategy_profile, params, start_date, end_date)
            except Exception:
                record.update(status="failed", reason="strict_backtest_failed")
                persist_trials()
                raise RuntimeError("cn_research_strict_backtest_failed") from None
            record.update(status="completed", reason=None)
            persist_trials()
            return result

    orchestrator = BacktestOrchestrator(store=store)
    orchestrator.register_runner("cn_equity", RecordedRunner())

    def optimize(drift, budget):
        if drift.strategy_profile != PROFILE or drift.domain != "cn_equity":
            raise ValueError("research_candidate_identity_mismatch")
        if budget.max_param_keys < len(BASELINE_PARAMS) or budget.max_search_iterations < 1:
            raise ValueError("research_budget_insufficient")
        proposal = run_grid_search(PROFILE, domain="cn_equity", orchestrator=orchestrator,
                                   search_space=SEARCH_SPACE, current_params=BASELINE_PARAMS,
                                   start_date=development_start, end_date=development_end,
                                   max_combinations=min(12, budget.max_search_iterations))
        # The shared search tolerates individual failed trials. A strict input
        # example must retain them and cannot call an incomplete search complete.
        if any(record["status"] != "completed" for record in trial_records):
            raise RuntimeError("cn_research_strict_trial_incomplete")
        store.save_proposal(proposal)
        return proposal

    return optimize


def make_index_etf_promotion_gate(
    *, data, development_end: date, folds, locked_oos_start: date, locked_oos_end: date,
    purge_days: int, embargo_days: int, source_revision: str, store, config, cost_model,
    trusted_historical_manifest_sha256: str,
):
    """Bind the existing QPK strict callback; no shadow or human result is invented.

    Parameters are selected before every fold. This rule strategy has no fitted
    model or future labels; fold training boundaries bound its initial history.
    The three folds validate the frozen rule, they do not retune a seen holdout.
    """
    from cn_equity_strategies.backtest.index_etf_strict_runner import CnIndexEtfBacktestRunner

    frozen_folds = tuple(folds)

    def enforce_backtest_gates(proposal):
        if proposal.strategy_profile != PROFILE or proposal.domain != "cn_equity":
            raise ValueError("research_candidate_identity_mismatch")
        if any(development_end >= fold.train_start for fold in frozen_folds):
            raise ValueError("strict_selection_overlaps_validation")
        runner = CnIndexEtfBacktestRunner(
            data, config=config, cost_model=cost_model, development_end=development_end,
            selected_params=proposal.proposed_params, folds=frozen_folds,
            locked_oos=(locked_oos_start, locked_oos_end),
            trusted_historical_manifest_sha256=trusted_historical_manifest_sha256,
        )
        orchestrator = BacktestOrchestrator(store=store)
        orchestrator.register_runner("cn_equity", runner)
        return orchestrator.run_promotion(
            PROFILE, domain="cn_equity", params=proposal.proposed_params, folds=frozen_folds,
            locked_oos_start=locked_oos_start, locked_oos_end=locked_oos_end,
            purge_days=purge_days, embargo_days=embargo_days, source_revision=source_revision,
            cost_model=cost_model,
        )

    return enforce_backtest_gates


def _definition_revision(value) -> str:
    import json
    from hashlib import sha256

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def index_etf_research_identity(
    *, development_input, validation_input, code_revision: str,
    development_start: date, development_end: date, folds,
    locked_oos_start: date, locked_oos_end: date, purge_days: int, embargo_days: int,
    config, cost_model,
) -> dict[str, str]:
    """Bind the five existing QPK resume keys to the actual input/definitions.

    These are reproducibility keys, not permission to use a source. The owning
    job separately verifies its repository revision and approved input roots.
    Source bytes also participate so a local edited checkout cannot reuse an
    old completed ticket merely by retaining its Git HEAD/version metadata.
    """
    import re
    from dataclasses import asdict
    from hashlib import sha256
    from pathlib import Path
    from quant_platform_kit.strategy_lifecycle import (
        backtest_orchestrator, contracts, evidence_gate, evidence_package_v2, param_optimizer, research_promotion_cycle,
    )
    from cn_equity_strategies.backtest import index_etf_strict_runner, proxy_simulator
    from cn_equity_strategies.strategies import cn_index_etf_tactical_rotation, etf_rotation_core

    if not isinstance(code_revision, str) or not re.fullmatch("[0-9a-f]{40}", code_revision):
        raise ValueError("cn_research_code_revision_required")

    def sources(modules):
        return {module.__name__: sha256(Path(module.__file__).read_bytes()).hexdigest() for module in modules}

    cn_sources = sources((index_etf_strict_runner, proxy_simulator, cn_index_etf_tactical_rotation, etf_rotation_core))
    cn_sources[__name__] = sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "code_revision": _definition_revision({"repository_revision": code_revision, "modules": cn_sources}),
        "input_revision": _definition_revision({
            "development": development_input.manifest_sha256, "validation": validation_input.manifest_sha256,
            "development_start": development_start.isoformat(), "development_end": development_end.isoformat(),
            "folds": [fold.to_dict() for fold in folds], "purge_days": purge_days, "embargo_days": embargo_days,
            "locked_oos_start": locked_oos_start.isoformat(), "locked_oos_end": locked_oos_end.isoformat(),
        }),
        "param_space_revision": _definition_revision({
            "search_space": SEARCH_SPACE.to_dict(), "baseline": BASELINE_PARAMS, "fixed": FIXED_STRATEGY_PARAMS,
            "optimizer": sources((param_optimizer,)), "max_grid_combinations": 12,
        }),
        "cost_model_revision": _definition_revision({
            "execution_config": asdict(config), "cost_model": cost_model.to_dict(),
            "execution_model": "next_open_daily_v1", "price_tick": .001, "cash_interest_rate": 0,
            "transaction_fees": "all_in_commission_with_minimum", "dividends": "net_cash_on_pay_date",
        }),
        "validator_revision": _definition_revision(sources((backtest_orchestrator, contracts, evidence_gate,
                                                            evidence_package_v2, research_promotion_cycle))),
    }



def preflight_index_etf_research_job(
    *, development_input, validation_input, trusted_input_roots,
    development_start: date, development_end: date, folds,
    locked_oos_start: date, locked_oos_end: date, purge_days: int, embargo_days: int,
    code_revision: str, config=None, cost_model=None,
) -> dict[str, str]:
    """Zero-model/zero-backtest preflight and the five actual QPK resume keys."""
    from collections.abc import Mapping
    from quant_platform_kit.strategy_lifecycle.contracts import PromotionCostModel
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import _validate_promotion_plan
    from cn_equity_strategies.backtest.index_etf_strict_runner import IndexEtfExecutionConfig, IndexEtfInput

    if (not isinstance(trusted_input_roots, Mapping) or set(trusted_input_roots) != {"development", "validation"}
            or any(not isinstance(data, IndexEtfInput) or data.evidence_kind != "historical"
                   or trusted_input_roots.get(name) != data.manifest_sha256
                   for name, data in (("development", development_input), ("validation", validation_input)))):
        raise ValueError("cn_research_approved_historical_inputs_required")
    config = config or IndexEtfExecutionConfig()
    cost_model = cost_model or PromotionCostModel("cn_index_etf.next_open.v1", 3., 5.)
    # This fixed dependency uses the same validator as run_promotion, not a
    # second interpretation of purge, embargo or locked-OOS boundaries.
    try:
        frozen_folds = _validate_promotion_plan(
            tuple(folds), locked_oos_start=locked_oos_start, locked_oos_end=locked_oos_end,
            purge_days=purge_days, embargo_days=embargo_days, source_revision=code_revision, cost_model=cost_model,
        )
    except (ValueError, TypeError, OverflowError):
        raise ValueError("cn_research_validation_plan_invalid") from None
    if (type(development_start) is not date or type(development_end) is not date
            or development_start >= development_end or development_input.sessions[-1] != development_end
            or sum(day < development_start for day in development_input.sessions) < 220
            or any(development_end >= fold.train_start for fold in frozen_folds)
            or validation_input.sessions[-1] < locked_oos_end
            or any(sum(fold.train_start <= day <= fold.train_end for day in validation_input.sessions) < 220
                   for fold in frozen_folds)):
        raise ValueError("cn_research_validation_partition_incomplete")
    return index_etf_research_identity(
        development_input=development_input, validation_input=validation_input, code_revision=code_revision,
        development_start=development_start, development_end=development_end, folds=frozen_folds,
        locked_oos_start=locked_oos_start, locked_oos_end=locked_oos_end,
        purge_days=purge_days, embargo_days=embargo_days, config=config, cost_model=cost_model,
    )

def run_index_etf_research_job(
    *, development_input, validation_input, trusted_input_roots,
    development_start: date, development_end: date, folds,
    locked_oos_start: date, locked_oos_end: date, purge_days: int, embargo_days: int,
    code_revision: str, ticket_dir, store_root, as_of, drift_score, source_revision,
    record_shadow, sync_console, diagnose=None, pull_console=None, admit_new_research=None, read_pending_shadow=None,
    config=None, cost_model=None, evaluation_date=None,
) -> dict[str, Any]:
    """Owning watcher's frozen job -> QPK's existing durable cycle.

    No command text/model result can select this configuration. The deployment
    binds historical roots only after approving provider/license/range evidence.
    AAB keeps its job/lease; QPK owns stage persistence. This is not a scheduler.
    """
    from pathlib import Path
    from collections.abc import Mapping
    from quant_platform_kit.strategy_lifecycle.contracts import PromotionCostModel
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore
    from quant_platform_kit.strategy_lifecycle.promotion_actionable_runner import run_actionable_research_promotion
    from cn_equity_strategies.backtest.index_etf_strict_runner import IndexEtfExecutionConfig, IndexEtfInput

    if not callable(record_shadow) or not callable(sync_console):
        raise ValueError("cn_research_downstream_bindings_required")
    config = config or IndexEtfExecutionConfig()
    cost_model = cost_model or PromotionCostModel("cn_index_etf.next_open.v1", 3., 5.)
    frozen_folds = tuple(folds)
    identity = preflight_index_etf_research_job(
        development_input=development_input, validation_input=validation_input, trusted_input_roots=trusted_input_roots,
        development_start=development_start, development_end=development_end, folds=frozen_folds,
        locked_oos_start=locked_oos_start, locked_oos_end=locked_oos_end,
        purge_days=purge_days, embargo_days=embargo_days, code_revision=code_revision, config=config, cost_model=cost_model,
    )
    # Keep artifact storage separate for distinct drift observations, just as
    # QPK keeps distinct tickets. This is an artifact path, not its resume key.
    experiment = _definition_revision({
        "research_identity": identity, "as_of": as_of.isoformat() if isinstance(as_of, date) else as_of,
        "source_revision": source_revision, "drift_score": drift_score,
    }).removeprefix("sha256:")
    experiment_store_root = Path(store_root) / "experiments" / experiment
    store = PerformanceStore(local_root=experiment_store_root)
    records = []
    trial_path = experiment_store_root / "trials.json"
    optimize = make_strict_index_etf_optimizer(
        data=development_input, development_start=development_start, development_end=development_end,
        store=store, trial_records=records, config=config, cost_model=cost_model, trial_path=trial_path,
    )
    gate = make_index_etf_promotion_gate(
        data=validation_input, development_end=development_end, folds=frozen_folds,
        locked_oos_start=locked_oos_start, locked_oos_end=locked_oos_end,
        purge_days=purge_days, embargo_days=embargo_days, source_revision=code_revision,
        store=store, config=config, cost_model=cost_model,
        trusted_historical_manifest_sha256=trusted_input_roots["validation"],
    )
    # A dependency without the persisted interface fails before any remote call.
    import inspect
    if not {"research_identity", "admit_new_research", "read_pending_shadow"} <= set(inspect.signature(run_actionable_research_promotion).parameters):
        raise ValueError("cn_research_persistent_qpk_required")
    result = run_actionable_research_promotion(
        strategy_profile=PROFILE, domain="cn_equity", as_of=as_of, drift_score=drift_score,
        source_revision=source_revision, evaluation_date=evaluation_date,
        optimize=optimize, enforce_backtest_gates=gate, record_shadow=record_shadow, sync_console=sync_console,
        diagnose=diagnose, pull_console=pull_console, research_identity=identity, ticket_dir=ticket_dir,
        admit_new_research=admit_new_research, read_pending_shadow=read_pending_shadow,
    )
    return {**result, "trial_records_path": str(trial_path), "experiment_store_root": str(experiment_store_root),
            "research_identity": identity,
            "benchmark_method": "monthly_target_510300_same_constraints",
            "live_ready": False, "size_zero_required": True, "no_order": True}
