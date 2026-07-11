#!/usr/bin/env python3
"""Run walk-forward backtests via QuantPlatformKit BacktestOrchestrator."""

from __future__ import annotations

import argparse
import copy
import json
import hashlib
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from quant_platform_kit.strategy_lifecycle.performance_metrics import compute_window_metrics

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner, SUPPORTED_PROFILES
from cn_equity_strategies.backtest.proxy_profile_registry import PROXY_PROFILE_REGISTRY

DEFAULT_WINDOWS: tuple[tuple[date, date], ...] = (
    (date(2023, 6, 1), date(2024, 5, 31)),
    (date(2024, 6, 1), date(2025, 5, 31)),
    (date(2025, 6, 1), date(2026, 3, 31)),
)
DEFAULT_STORE_ROOT = Path("/tmp/cn_equity_wf_store")
DRIFT_BASELINE_HORIZON_DAYS = 126


def _default_params(profile: str) -> dict[str, Any]:
    spec = PROXY_PROFILE_REGISTRY[profile]
    return {"min_history_days": spec.default_min_history_days}


def _result_payload(item: Any) -> dict[str, Any]:
    return {
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "sharpe_ratio": item.sharpe_ratio,
        "max_drawdown": item.max_drawdown,
        "cagr": item.cagr,
        "total_return": item.total_return,
        "observation_count": item.observation_count,
        "run_id": item.run_id,
    }


def _baseline_param_set_id(
    profile: str,
    params: dict[str, Any],
    *,
    synthetic_days: int,
    windows: tuple[tuple[date, date], ...] = DEFAULT_WINDOWS,
    data_fingerprint: str = "",
) -> str:
    identity = {
        "params": params,
        "data_fingerprint": data_fingerprint or f"synthetic:{synthetic_days}",
        "windows": [(start.isoformat(), end.isoformat()) for start, end in windows],
        "drift_baseline_horizon_days": DRIFT_BASELINE_HORIZON_DAYS,
    }
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"{profile}_baseline_{fingerprint}"


def _build_runner(*, synthetic_days: int, market_history: pd.DataFrame | None = None) -> CnProxyBacktestRunner:
    return CnProxyBacktestRunner(
        synthetic_days=synthetic_days,
        market_history=market_history.copy(deep=True) if market_history is not None else None,
    )


def _normalize_market_history(market_history: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(market_history).copy()
    if "date" not in frame.columns and "as_of" in frame.columns:
        frame = frame.rename(columns={"as_of": "date"})
    required = {"date", "symbol", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"market history is missing columns: {', '.join(missing)}")
    frame = frame[["date", "symbol", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame["symbol"] = frame["symbol"].map(_normalize_symbol)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna().drop_duplicates(["date", "symbol"], keep="last").sort_values(["date", "symbol"])


def _normalize_symbol(value: object) -> str:
    text = str(value or "").strip().upper()
    if text.endswith((".SH", ".SZ")):
        text = text.rsplit(".", 1)[0]
    return text.zfill(6) if text.isdigit() else text


def _market_history_fingerprint(market_history: pd.DataFrame) -> str:
    normalized = _normalize_market_history(market_history)
    digest = hashlib.sha256(pd.util.hash_pandas_object(normalized, index=False).values.tobytes()).hexdigest()
    return digest[:16]


def _shared_market_history(
    profile: str,
    params: dict[str, Any],
    windows: tuple[tuple[date, date], ...],
    market_history: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    min_history_days = int(params["min_history_days"])
    earliest_window_start = min(start for start, _ in windows)
    lookback_start = earliest_window_start - pd.tseries.offsets.BDay(min_history_days + 5)
    history = _normalize_market_history(market_history)
    available_end = history["date"].max()
    history = history.loc[
        (history["date"] >= pd.Timestamp(lookback_start))
        & (history["date"] <= available_end)
    ].copy()
    required_symbols = {_normalize_symbol(symbol) for symbol in PROXY_PROFILE_REGISTRY[profile].extract_managed_symbols()}
    required_symbols.add("510300")
    history = history.loc[history["symbol"].isin(required_symbols)].copy()
    missing_symbols = sorted(required_symbols - set(history["symbol"]))
    if missing_symbols:
        raise ValueError(f"market history is missing required symbols: {', '.join(missing_symbols)}")
    reference_symbol = "510300" if "510300" in required_symbols else sorted(required_symbols)[0]
    reference_dates = set(history.loc[history["symbol"] == reference_symbol, "date"])
    if not reference_dates:
        raise ValueError(f"market history is missing {reference_symbol} reference dates")
    expected_business_dates = pd.bdate_range(lookback_start, available_end)
    if (
        len(reference_dates) / len(expected_business_dates) < 0.85
        or max(reference_dates) < pd.Timestamp(available_end) - pd.Timedelta(days=7)
    ):
        raise ValueError("market history has incomplete 510300 reference coverage")
    first_required_day = min(reference_dates)
    latest_required_day = max(reference_dates)
    incomplete_symbols: list[str] = []
    for symbol in sorted(required_symbols):
        symbol_dates = set(history.loc[history["symbol"] == symbol, "date"])
        coverage_ratio = len(symbol_dates & reference_dates) / len(reference_dates)
        if (
            not symbol_dates
            or min(symbol_dates) > first_required_day
            or max(symbol_dates) < latest_required_day
            or coverage_ratio < 0.98
        ):
            incomplete_symbols.append(symbol)
    if incomplete_symbols:
        raise ValueError(f"market history has incomplete symbol coverage: {', '.join(incomplete_symbols)}")
    return history, _market_history_fingerprint(history)


def _write_return_matrix(
    output_path: Path,
    *,
    profile: str,
    returns: pd.Series,
    market_history: pd.DataFrame,
) -> None:
    frame = returns.rename(profile).to_frame()
    benchmark = _normalize_market_history(market_history)
    benchmark = benchmark.loc[benchmark["symbol"] == "510300"].set_index("date")["close"].pct_change()
    frame["buy_hold_510300"] = benchmark.reindex(frame.index)
    frame.index.name = "as_of"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_csv(output_path, index=False)


def _baseline_from_return_tail(full_result: Any, returns: pd.Series) -> Any:
    tail = returns.tail(DRIFT_BASELINE_HORIZON_DAYS)
    metrics = compute_window_metrics(tail, window_days=DRIFT_BASELINE_HORIZON_DAYS)
    max_drawdown = float(metrics.max_drawdown)
    cagr = float(metrics.cagr)
    return replace(
        full_result,
        sharpe_ratio=float(metrics.sharpe_ratio),
        calmar_ratio=float(metrics.calmar_ratio),
        max_drawdown=max_drawdown,
        cagr=cagr,
        volatility=float(metrics.volatility),
        win_rate=float(metrics.win_rate),
        total_return=float(metrics.total_return),
        start_date=metrics.start_date,
        end_date=metrics.end_date,
        observation_count=metrics.observation_count,
    )


def run_walk_forward(
    *,
    profile: str,
    windows: tuple[tuple[date, date], ...] = DEFAULT_WINDOWS,
    synthetic_days: int = 900,
    compare_tolerance: float = 0.001,
    store_root: Path | None = None,
    market_history: pd.DataFrame | None = None,
    returns_output: Path | None = None,
) -> dict[str, Any]:
    from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
    from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore

    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported profile={profile!r}; supported={sorted(SUPPORTED_PROFILES)}")

    params = _default_params(profile)
    target_root = store_root or DEFAULT_STORE_ROOT
    target_root.mkdir(parents=True, exist_ok=True)
    baseline_params = copy.deepcopy(params)
    data_fingerprint = f"synthetic:{synthetic_days}"
    shared_market_history = None
    if market_history is not None:
        shared_market_history, data_fingerprint = _shared_market_history(
            profile,
            baseline_params,
            windows,
            market_history,
        )
    return_matrix_runner = _build_runner(synthetic_days=synthetic_days, market_history=shared_market_history)
    full_window_start = min(start for start, _ in windows)
    baseline_end = max(end for _, end in windows)
    full_window_raw = return_matrix_runner.run(
        profile,
        baseline_params,
        start_date=full_window_start,
        end_date=baseline_end,
    )
    full_window_returns = return_matrix_runner.last_daily_returns
    if len(full_window_returns) < DRIFT_BASELINE_HORIZON_DAYS:
        raise ValueError("full-window returns do not cover the 126-day drift baseline")
    baseline_raw = _baseline_from_return_tail(full_window_raw, full_window_returns)
    with tempfile.TemporaryDirectory(prefix=f"{profile}_wf_", dir=target_root) as scratch_dir:
        scratch_store = PerformanceStore(local_root=Path(scratch_dir))
        scratch_orchestrator = BacktestOrchestrator(store=scratch_store)
        scratch_orchestrator.register_runner(
            "cn_equity",
            _build_runner(synthetic_days=synthetic_days, market_history=shared_market_history),
        )
        via_orch = scratch_orchestrator.run(
            profile,
            domain="cn_equity",
            params=copy.deepcopy(baseline_params),
            param_set_id=f"{profile}_full_compare",
            start_date=full_window_start,
            end_date=baseline_end,
        )
        wf_params = copy.deepcopy(baseline_params)
        wf_results = scratch_orchestrator.walk_forward(
            profile,
            domain="cn_equity",
            params=wf_params,
            windows=windows,
            param_set_id=f"{profile}_wf",
        )
    sharpe_delta = abs(float(via_orch.sharpe_ratio or 0.0) - float(full_window_raw.sharpe_ratio or 0.0))
    mdd_delta = abs(float(via_orch.max_drawdown or 0.0) - float(full_window_raw.max_drawdown or 0.0))
    within_tolerance = sharpe_delta <= compare_tolerance and mdd_delta <= compare_tolerance
    if not within_tolerance:
        raise RuntimeError(
            "baseline comparison failed: "
            f"sharpe_delta={sharpe_delta:.6f}, max_drawdown_delta={mdd_delta:.6f}, "
            f"tolerance={compare_tolerance:.6f}"
        )
    store = PerformanceStore(local_root=target_root)
    orchestrator = BacktestOrchestrator(store=store)
    baseline = orchestrator.persist_result(
        baseline_raw,
        strategy_profile=profile,
        domain="cn_equity",
        params=baseline_params,
        param_set_id=_baseline_param_set_id(
            profile,
            baseline_params,
            synthetic_days=synthetic_days,
            windows=windows,
            data_fingerprint=data_fingerprint,
        ),
    )
    if returns_output is not None:
        if shared_market_history is None:
            raise ValueError("returns_output requires market_history")
        current_end = shared_market_history["date"].max().date()
        current_runner = _build_runner(
            synthetic_days=synthetic_days,
            market_history=shared_market_history,
        )
        current_runner.run(
            profile,
            copy.deepcopy(baseline_params),
            start_date=full_window_start,
            end_date=current_end,
        )
        _write_return_matrix(
            returns_output,
            profile=profile,
            returns=current_runner.last_daily_returns,
            market_history=shared_market_history,
        )

    return {
        "strategy_profile": profile,
        "domain": "cn_equity",
        "baseline": _result_payload(baseline),
        "orchestrator_full_window": _result_payload(via_orch),
        "walk_forward_folds": [_result_payload(item) for item in wf_results],
        "compare": {
            "sharpe_delta": sharpe_delta,
            "max_drawdown_delta": mdd_delta,
            "tolerance": compare_tolerance,
            "within_tolerance": within_tolerance,
        },
        "source": "BacktestOrchestrator.walk_forward",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CN walk-forward backtest via BacktestOrchestrator.")
    parser.add_argument("--profile", default="cn_index_etf_tactical_rotation")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--synthetic-days", type=int, default=900)
    parser.add_argument("--tolerance", type=float, default=0.001)
    parser.add_argument("--store-root", type=Path)
    parser.add_argument("--market-history", type=Path)
    parser.add_argument("--returns-output", type=Path)
    args = parser.parse_args()

    if args.list_profiles:
        print(json.dumps({"profiles": sorted(SUPPORTED_PROFILES)}, indent=2))
        return 0

    market_history = pd.read_csv(args.market_history) if args.market_history else None
    payload = run_walk_forward(
        profile=args.profile,
        synthetic_days=args.synthetic_days,
        compare_tolerance=args.tolerance,
        store_root=args.store_root,
        market_history=market_history,
        returns_output=args.returns_output,
    )
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n")
    print(text)
    if not payload["compare"]["within_tolerance"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
