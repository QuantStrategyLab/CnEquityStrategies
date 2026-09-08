"""Daily-bar execution model for the fixed CN index ETF research candidate.

Signals use causal total-return prices; orders use unadjusted next-session
opens. Daily volume only limits the *following* session's simulated fills.
This model does not claim exchange queue priority or observed broker fills.
Input publication/ETL belongs to CnEquitySnapshotPipelines, not this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import math
from typing import Any, Mapping
from types import MappingProxyType

import pandas as pd
from quant_platform_kit.data.research_input import read_research_input_manifest_json, research_input_manifest_sha256
from quant_platform_kit.strategy_lifecycle.contracts import BacktestResult, PromotionCostModel, PurgedWalkForwardFold

from cn_equity_strategies.backtest.proxy_simulator import _commission, _round_lot, compute_backtest_metrics
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import build_target_weights

PROFILE = "cn_index_etf_tactical_rotation"
SYMBOLS = ("510300", "510500")
BENCHMARK_METHOD = "monthly_target_510300_same_constraints"
INPUT_CONTRACT = "qsl.cn_index_etf.execution_input.v1"
REQUIRED_MEMBERS = frozenset({"normalized/daily.json", "calendar/sessions.json", "corporate_actions/events.json",
                              "evidence/license.bin", "evidence/license_identity.json"})
BAR_FIELDS = frozenset({"date", "symbol", "open", "high", "low", "close", "volume", "suspended",
                        "limit_up", "limit_down", "status_known_at", "available_at"})
ACTION_FIELDS = frozenset({"symbol", "record_date", "ex_date", "pay_date", "cash_per_share", "split_ratio", "known_at"})


def _number(value: Any, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise ValueError("cn_execution_number_invalid")
    return float(value)


def _day(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("cn_execution_date_invalid")
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("cn_execution_date_invalid")
    return result


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("cn_execution_timestamp_invalid")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("cn_execution_timestamp_invalid")
    return result


def _at(day: date, clock: str) -> datetime:
    return datetime.fromisoformat(f"{day.isoformat()}T{clock}+08:00")


def _json(payload: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("cn_execution_json_invalid")
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("cn_execution_json_invalid")))


@dataclass(frozen=True)
class IndexEtfInput:
    """Validated input copied from an externally selected manifest root.

    Manifest binding verifies bytes, not the truth of a provider's claim. The
    caller must select the root from the approved producer, never from a model.
    """
    manifest_sha256: str
    evidence_kind: str
    sessions: tuple[date, ...]
    _rows: tuple[Mapping[str, Any], ...] = field(repr=False)
    _actions: tuple[Mapping[str, Any], ...] = field(repr=False)

    def signal_history(self, end_date: date) -> pd.DataFrame:
        prices = {symbol: None for symbol in SYMBOLS}
        adjusted = {symbol: None for symbol in SYMBOLS}
        events = {(item["ex_date"], item["symbol"]): item for item in self._actions}
        output = []
        for row in self._rows:
            if row["date"] > end_date:
                break
            symbol, close = row["symbol"], row["close"]
            action = events.get((row["date"], symbol), {})
            if prices[symbol] is None:
                adjusted[symbol] = close
            else:
                adjusted[symbol] *= (close * action.get("split_ratio", 1) + action.get("cash_per_share", 0)) / prices[symbol]
            prices[symbol] = close
            output.append({"date": pd.Timestamp(row["date"]), "symbol": symbol, "close": adjusted[symbol]})
        return pd.DataFrame(output)


def load_index_etf_input(manifest_bytes: bytes, members: Mapping[str, bytes], *, expected_manifest_sha256: str) -> IndexEtfInput:
    """Validate the existing QPK manifest and the CN execution member contract.

    All failures are fixed reasons; neither raw records nor supplier messages
    are included. No provider, model, file write or implicit fill is performed.
    """
    try:
        manifest = read_research_input_manifest_json(manifest_bytes)
        if research_input_manifest_sha256(manifest) != expected_manifest_sha256:
            raise ValueError("cn_execution_manifest_identity_invalid")
        if (manifest["research_input_contract_id"] != INPUT_CONTRACT or manifest["profile"] != PROFILE
                or manifest["domain"] != "cn_equity" or manifest["adjustment"]["policy"] != "raw"
                or manifest["calendar"]["timezone"] != "Asia/Shanghai"
                or manifest["producer"]["repository"] != "QuantStrategyLab/CnEquitySnapshotPipelines"
                or manifest["artifact_type"] not in {"cn_index_etf_execution_history", "cn_index_etf_synthetic_execution_history"}):
            raise ValueError("cn_execution_manifest_identity_invalid")
        listed = {item["path"]: item for item in manifest["members"]}
        if set(listed) != set(members) or not REQUIRED_MEMBERS <= set(listed):
            raise ValueError("cn_execution_member_identity_invalid")
        for path, member in listed.items():
            content = members[path]
            if not isinstance(content, bytes) or len(content) != member["size_bytes"] or sha256(content).hexdigest() != member["sha256"]:
                raise ValueError("cn_execution_member_identity_invalid")
        license_info = _json(members["evidence/license_identity.json"])
        if (not isinstance(license_info, dict)
                or license_info.get("retention_scope") != "private-retention-permitted"
                or not isinstance(license_info.get("source_identity"), str)
                or not license_info["source_identity"].startswith("official:")
                or not isinstance(license_info.get("revision"), str) or not license_info["revision"].strip()
                or license_info.get("content_sha256") != listed["evidence/license.bin"]["sha256"]
                or len(members["evidence/license.bin"].strip()) < 20):
            raise ValueError("cn_execution_license_evidence_invalid")
        calendar = _json(members["calendar/sessions.json"])
        if set(calendar) != {"start_date", "end_date", "sessions"}:
            raise ValueError("cn_execution_calendar_invalid")
        sessions = tuple(_day(day) for day in calendar["sessions"])
        if (not sessions or sessions != tuple(sorted(set(sessions)))
                or sessions[0] != _day(calendar["start_date"]) or sessions[-1] != _day(calendar["end_date"])
                or any(day.weekday() >= 5 for day in sessions)
                or manifest["calendar"]["source_revision"] != "sha256:" + listed["calendar/sessions.json"]["sha256"]
                or manifest["calendar"]["session_date"] != sessions[-1].isoformat()):
            raise ValueError("cn_execution_calendar_invalid")
        observed = _timestamp(manifest["as_of"])
        rows = _json(members["normalized/daily.json"])
        if not isinstance(rows, list):
            raise ValueError("cn_execution_history_invalid")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != BAR_FIELDS or row["symbol"] not in SYMBOLS:
                raise ValueError("cn_execution_history_invalid")
            row["date"] = day = _day(row["date"])
            key = (day, row["symbol"])
            if key in seen:
                raise ValueError("cn_execution_history_duplicate")
            seen.add(key)
            for field_name in ("open", "high", "low", "close", "limit_up", "limit_down"):
                row[field_name] = _number(row[field_name], positive=True)
            row["volume"] = _number(row["volume"])
            if (type(row["suspended"]) is not bool or row["limit_down"] >= row["limit_up"]
                    or row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"])
                    or row["low"] < row["limit_down"] - 1e-9 or row["high"] > row["limit_up"] + 1e-9
                    or (row["suspended"] and row["volume"] != 0)):
                raise ValueError("cn_execution_history_invalid")
            if (not _at(day, "00:00:00") <= _timestamp(row["status_known_at"]) <= _at(day, "09:25:00")
                    or not _at(day, "15:00:00") <= _timestamp(row["available_at"]) <= _at(day, "16:00:00")
                    or _timestamp(row["available_at"]) > observed):
                raise ValueError("cn_execution_availability_invalid")
        if seen != {(day, symbol) for day in sessions for symbol in SYMBOLS}:
            raise ValueError("cn_execution_session_coverage_incomplete")
        actions = _json(members["corporate_actions/events.json"])
        if (set(actions) != {"complete_from", "complete_through", "events"}
                or _day(actions["complete_from"]) != sessions[0] or _day(actions["complete_through"]) != sessions[-1]
                or not isinstance(actions["events"], list)):
            raise ValueError("cn_execution_corporate_actions_incomplete")
        action_keys = set()
        for event in actions["events"]:
            if not isinstance(event, dict) or set(event) != ACTION_FIELDS or event["symbol"] not in SYMBOLS:
                raise ValueError("cn_execution_corporate_action_unsupported")
            for name in ("record_date", "ex_date", "pay_date"):
                event[name] = _day(event[name])
            key = (event["ex_date"], event["symbol"])
            if (key in action_keys or event["ex_date"] not in sessions[1:]
                    or event["record_date"] != sessions[sessions.index(event["ex_date"]) - 1]
                    or event["pay_date"] < event["ex_date"]
                    or type(event["split_ratio"]) is not int or event["split_ratio"] < 1
                    or _timestamp(event["known_at"]) > _at(event["ex_date"], "09:25:00")):
                raise ValueError("cn_execution_corporate_action_unsupported")
            event["cash_per_share"] = _number(event["cash_per_share"])
            action_keys.add(key)
        return IndexEtfInput(expected_manifest_sha256,
                             "synthetic" if manifest["artifact_type"].startswith("cn_index_etf_synthetic") else "historical",
                             sessions, tuple(MappingProxyType(row) for row in sorted(rows, key=lambda row: (row["date"], row["symbol"]))),
                             tuple(MappingProxyType(event) for event in sorted(actions["events"], key=lambda event: (event["ex_date"], event["symbol"]))))
    except (KeyError, TypeError, UnicodeError, OverflowError, ValueError) as error:
        reason = str(error) if isinstance(error, ValueError) and str(error).startswith("cn_execution_") else "cn_execution_input_invalid"
        raise ValueError(reason) from None


def read_index_etf_input(package_root: str | Path, *, expected_manifest_sha256: str) -> IndexEtfInput:
    """Read one explicit local package; provider access remains in its producer."""
    try:
        root = Path(package_root).resolve(strict=True)
        manifest_path = root / "research_input_manifest.v1.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 1_000_000:
            raise ValueError("cn_execution_input_invalid")
        encoded = manifest_path.read_bytes()
        manifest = read_research_input_manifest_json(encoded)
        if research_input_manifest_sha256(manifest) != expected_manifest_sha256:
            raise ValueError("cn_execution_manifest_identity_invalid")
        members = {}
        if sum(member["size_bytes"] for member in manifest["members"]) > 64_000_000:
            raise ValueError("cn_execution_input_invalid")
        for member in manifest["members"]:
            path = root / member["path"]
            if (path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)
                    or path.stat().st_size != member["size_bytes"]):
                raise ValueError("cn_execution_member_identity_invalid")
            members[member["path"]] = path.read_bytes()
        return load_index_etf_input(encoded, members, expected_manifest_sha256=expected_manifest_sha256)
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("cn_execution_local_package_invalid") from None


@dataclass(frozen=True)
class IndexEtfExecutionConfig:
    initial_cash: float = 1_000_000.0
    minimum_commission: float = 5.0
    cash_reserve_ratio: float = 0.02
    max_previous_volume_participation: float = 0.01
    lot_size: int = 100

    def __post_init__(self):
        _number(self.initial_cash, positive=True)
        _number(self.minimum_commission)
        if (not 0 <= _number(self.cash_reserve_ratio) < 1
                or not 0 < _number(self.max_previous_volume_participation) <= 1
                or type(self.lot_size) is not int or self.lot_size != 100):
            raise ValueError("cn_execution_config_invalid")


@dataclass
class IndexEtfSimulation:
    daily_returns: pd.Series
    ledger: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    unfilled: list[dict[str, Any]]
    final_cash: float
    final_holdings: dict[str, int]
    total_fees: float
    metrics: Mapping[str, Any]


class CnIndexEtfBacktestRunner:
    """Explicit QPK adapter; fixed rules, no fitting on validation/locked OOS.

    Promotion methods require an independently frozen parameter selection and
    plan. Synthetic input never advertises QPK's ``runner_kind='real'``.
    """
    def __init__(self, data: IndexEtfInput, *, config: IndexEtfExecutionConfig | None = None,
                 cost_model: PromotionCostModel | None = None, development_end: date | None = None,
                 selected_params: Mapping[str, Any] | None = None,
                 folds: tuple[PurgedWalkForwardFold, ...] = (), locked_oos: tuple[date, date] | None = None,
                 trusted_historical_manifest_sha256: str | None = None):
        self._data = data
        self.config = config or IndexEtfExecutionConfig()
        self.cost_model = cost_model or PromotionCostModel("cn_index_etf.next_open.v1", 3.0, 5.0)
        self.development_end = development_end
        self._selected_params = dict(selected_params) if selected_params is not None else None
        self._folds = tuple(folds)
        self._locked_oos = locked_oos
        # This root comes from the owning job's approved source configuration,
        # never from a manifest field, CLI flag or model recommendation.
        self._trusted_historical_manifest_sha256 = trusted_historical_manifest_sha256
        self.last_simulation: IndexEtfSimulation | None = None

    @property
    def runner_kind(self):
        if self._data.evidence_kind == "synthetic":
            return "synthetic"
        return "real" if self._trusted_historical_manifest_sha256 == self._data.manifest_sha256 else "unverified"

    def simulate_targets(self, targets: Mapping[date, Mapping[str, float]], *, start_date: date, end_date: date,
                         cost_model: PromotionCostModel) -> IndexEtfSimulation:
        """Pure local numeric entry; target dates are 16:00 decision timestamps.

        Ledger/trades contain private per-day series: callers must not put them
        in logs, public artifacts, or unapproved storage. Results are simulations.
        """
        for name in ("commission_bps", "slippage_bps", "market_impact_bps"):
            _number(getattr(cost_model, name))
        slip = (cost_model.slippage_bps + cost_model.market_impact_bps) / 10000
        if slip >= 1 or type(start_date) is not date or type(end_date) is not date or start_date > end_date:
            raise ValueError("cn_execution_window_or_cost_invalid")
        sessions = self._data.sessions
        evaluation = [day for day in sessions if start_date <= day <= end_date]
        if not evaluation or start_date < sessions[0] or end_date > sessions[-1]:
            raise ValueError("cn_execution_window_missing")
        first = sessions.index(evaluation[0])
        if first == 0:
            raise ValueError("cn_execution_prior_session_missing")
        valid_decisions = set(sessions[first-1:sessions.index(evaluation[-1])+1])
        for day, weights in targets.items():
            if type(day) is not date or day not in valid_decisions or not isinstance(weights, Mapping):
                raise ValueError("cn_execution_target_invalid")
            if set(weights) - set(SYMBOLS) or sum(_number(w) for w in weights.values()) > 1 + 1e-12:
                raise ValueError("cn_execution_target_invalid")
        rows = {(r["date"], r["symbol"]): r for r in self._data._rows}
        events = {(e["ex_date"], e["symbol"]): e for e in self._data._actions}
        cash = previous_equity = self.config.initial_cash
        holdings: dict[str, int] = {}
        receivables: list[tuple[date, float]] = []
        pending = None
        ledger, trades, unfilled = [], [], []
        returns = {}
        total_fees = 0.0
        for day in sessions[first-1:sessions.index(evaluation[-1])+1]:
            for symbol in SYMBOLS:
                event = events.get((day, symbol))
                if event:
                    before = holdings.get(symbol, 0)
                    if before:
                        receivables.append((event["pay_date"], before * event["cash_per_share"]))
                        holdings[symbol] = before * event["split_ratio"]
            cash += sum(amount for payable, amount in receivables if payable <= day)
            receivables = [(payable, amount) for payable, amount in receivables if payable > day]
            if pending is not None and day >= start_date:
                signal_day, quantities, capacity = pending
                # Corporate actions change existing shares and outstanding targets
                # consistently, without reallocating or spending dividends early.
                desired = {s: q * events.get((day, s), {}).get("split_ratio", 1) for s, q in quantities.items()}
                for side in ("sell", "buy"):
                    for symbol in SYMBOLS:
                        current = holdings.get(symbol, 0)
                        delta = desired.get(symbol, 0) - current
                        if (side == "sell" and delta >= 0) or (side == "buy" and delta <= 0):
                            continue
                        row = rows[day, symbol]
                        reason = "suspended" if row["suspended"] else (
                            "limit_up" if side == "buy" and row["open"] >= row["limit_up"] - 1e-9 else
                            "limit_down" if side == "sell" and row["open"] <= row["limit_down"] + 1e-9 else "")
                        price = row["open"] * (1 + slip if side == "buy" else 1 - slip)
                        # Round simulated ETF prices adversely to the exchange tick.
                        price = (math.ceil(price * 1000 - 1e-9) if side == "buy" else math.floor(price * 1000 + 1e-9)) / 1000
                        if price > row["limit_up"] + 1e-9 or price < row["limit_down"] - 1e-9:
                            reason = reason or "slippage_outside_limit"
                        requested = abs(delta)
                        quantity = _round_lot(min(requested, capacity[symbol]), self.config.lot_size)
                        if reason:
                            quantity = 0
                        if side == "buy":
                            affordable = min(max(cash - self.config.minimum_commission, 0) / price,
                                             cash / (price * (1 + cost_model.commission_bps / 10000)))
                            quantity = min(quantity, _round_lot(affordable, self.config.lot_size))
                        if quantity:
                            fee = _commission(quantity * price, rate=cost_model.commission_bps / 10000,
                                              minimum=self.config.minimum_commission)
                            cash += quantity * price - fee if side == "sell" else -quantity * price - fee
                            holdings[symbol] = current - quantity if side == "sell" else current + quantity
                            if not holdings[symbol]:
                                holdings.pop(symbol)
                            total_fees += fee
                            trades.append(dict(signal_date=signal_day, execution_date=day, symbol=symbol, side=side,
                                               quantity=quantity, price=price, fee=fee))
                        if quantity < requested:
                            unfilled.append(dict(signal_date=signal_day, execution_date=day, symbol=symbol, side=side,
                                                 quantity=requested-quantity, reason=reason or "capacity_or_cash"))
                pending = None  # one-session order; residual is cancelled, never silently retried
            equity = cash + sum(holdings.get(symbol, 0) * rows[day, symbol]["close"] for symbol in SYMBOLS) + sum(a for _, a in receivables)
            if not math.isfinite(equity) or equity <= 0 or cash < -1e-7:
                raise ValueError("cn_execution_accounting_invalid")
            if day >= start_date:
                returns[pd.Timestamp(day)] = equity / previous_equity - 1
                ledger.append(dict(date=day, cash=cash, holdings=dict(holdings), receivables=sum(a for _, a in receivables), equity=equity))
                previous_equity = equity
            if day in targets:
                quantities = {symbol: _round_lot(equity * (1-self.config.cash_reserve_ratio) * targets[day].get(symbol, 0) /
                                                  rows[day, symbol]["close"], self.config.lot_size) for symbol in SYMBOLS}
                capacity = {symbol: _round_lot(rows[day, symbol]["volume"] * self.config.max_previous_volume_participation,
                                               self.config.lot_size) for symbol in SYMBOLS}
                pending = day, quantities, capacity
        series = pd.Series(returns, dtype=float)
        return IndexEtfSimulation(series, ledger, trades, unfilled, cash, holdings, total_fees, compute_backtest_metrics(series))

    def _run(self, strategy_profile, params, start_date, end_date, cost_model, *, history_start=None):
        from cn_equity_strategies.backtest.index_etf_research_job import FIXED_STRATEGY_PARAMS
        allowed = {"momentum_window_days": {40, 60, 80}, "trend_window_days": {120, 200}, "top_n": {1, 2}}
        if (strategy_profile != PROFILE or set(params) != set(allowed)
                or any(type(params[key]) is not int or params[key] not in values for key, values in allowed.items())):
            raise ValueError("cn_execution_strategy_invalid")
        if type(start_date) is not date or type(end_date) is not date:
            raise ValueError("cn_execution_window_required")
        history = self._data.signal_history(end_date)
        if history_start is not None:
            history = history.loc[history["date"] >= pd.Timestamp(history_start)]
        sessions = self._data.sessions
        evaluation = [day for day in sessions if start_date <= day <= end_date]
        if not evaluation or sessions.index(evaluation[0]) < FIXED_STRATEGY_PARAMS["min_history_days"]:
            raise ValueError("cn_execution_warmup_incomplete")
        initial_decision = sessions[sessions.index(evaluation[0])-1]
        decisions = [initial_decision] + [day for i, day in enumerate(sessions[:-1])
                                          if start_date <= day < end_date and day.month != sessions[i+1].month]
        targets = {}
        for day in decisions:
            visible = history.loc[history["date"] <= pd.Timestamp(day)]
            targets[day], _ = build_target_weights(visible, **{**FIXED_STRATEGY_PARAMS, **dict(params)})
        simulation = self.simulate_targets(targets, start_date=start_date, end_date=end_date, cost_model=cost_model)
        # Fixed 510300 target comparator shares the same monthly decisions,
        # reserve, costs and participation cap; it is not frictionless buy/hold.
        benchmark = self.simulate_targets({day: {"510300": 1.0} for day in decisions},
                                          start_date=start_date, end_date=end_date, cost_model=cost_model)
        self.last_simulation = simulation
        metrics = simulation.metrics
        return BacktestResult(strategy_profile=PROFILE, domain="cn_equity", param_set_id="", params=dict(params),
                              sharpe_ratio=metrics["sharpe_ratio"], cagr=metrics["annual_return"],
                              calmar_ratio=metrics["annual_return"] / abs(metrics["max_drawdown"]) if metrics["max_drawdown"] else None,
                              max_drawdown=metrics["max_drawdown"], volatility=metrics["annual_volatility"],
                              total_return=metrics["total_return"], observation_count=metrics["days"],
                              start_date=start_date, end_date=end_date, benchmark_symbol="510300",
                              benchmark_cagr=benchmark.metrics["annual_return"],
                              benchmark_max_drawdown=benchmark.metrics["max_drawdown"],
                              excess_cagr=metrics["annual_return"]-benchmark.metrics["annual_return"],
                              source_script=__name__, computed_at=datetime.now(timezone.utc).isoformat())

    def run(self, strategy_profile, params, start_date=None, end_date=None):
        if self.development_end is None or end_date is None or end_date > self.development_end:
            raise ValueError("cn_execution_development_boundary_required")
        return self._run(strategy_profile, params, start_date, end_date, self.cost_model)

    def _promotion_identity(self, params):
        if (self.runner_kind != "real" or self.development_end is None or self._selected_params is None
                or dict(params) != self._selected_params or len(self._folds) < 3 or self._locked_oos is None
                or any(self.development_end >= fold.train_start for fold in self._folds)):
            raise ValueError("cn_execution_promotion_identity_invalid")

    def run_purged_fold(self, strategy_profile, params, *, fold, purge_days, embargo_days, cost_model):
        self._promotion_identity(params)
        if (fold not in self._folds or type(purge_days) is not int or type(embargo_days) is not int
                or purge_days <= 0 or embargo_days <= 0 or fold.train_end + timedelta(days=purge_days) >= fold.test_start):
            raise ValueError("cn_execution_promotion_plan_invalid")
        if sum(fold.train_start <= day <= fold.train_end for day in self._data.sessions) < 220:
            raise ValueError("cn_execution_fold_training_warmup_incomplete")
        return self._run(strategy_profile, params, fold.test_start, fold.test_end, cost_model, history_start=fold.train_start)

    def run_locked_oos(self, strategy_profile, params, *, start_date, end_date, cost_model):
        self._promotion_identity(params)
        if (start_date, end_date) != self._locked_oos:
            raise ValueError("cn_execution_locked_oos_identity_invalid")
        return self._run(strategy_profile, params, start_date, end_date, cost_model)
