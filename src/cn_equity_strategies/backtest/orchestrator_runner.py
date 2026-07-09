"""BacktestRunner adapter that wraps CN proxy backtests for QuantPlatformKit."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

import pandas as pd

from cn_equity_strategies.backtest.proxy_profile_registry import PROXY_PROFILE_REGISTRY, SUPPORTED_PROFILES
from cn_equity_strategies.backtest.proxy_simulator import ProxyBacktestConfig, run_proxy_backtest

try:
    from quant_platform_kit.strategy_lifecycle.contracts import BacktestResult
except ImportError:  # pragma: no cover - exercised only without QPK installed
    BacktestResult = None  # type: ignore[misc, assignment]


def _synthetic_market_history(
    *,
    extract_managed_symbols: Any,
    days: int = 900,
    start: str = "2022-01-03",
) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=days)
    symbols = tuple(extract_managed_symbols())
    rates = {symbol: 1.0002 + (idx * 0.00005) for idx, symbol in enumerate(symbols)}
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        price = 10.0 + (hash(symbol) % 7)
        rate = rates.get(symbol, 1.0002)
        for idx, day in enumerate(dates):
            price *= rate
            close = price * (1.0 + 0.03 * ((idx % 7) - 3) / 7)
            rows.append({"date": day, "symbol": symbol, "close": close})
    return pd.DataFrame(rows)


def _slice_history(
    market_history: pd.DataFrame,
    *,
    start_date: date | None,
    end_date: date | None,
    lookback_days: int = 0,
) -> pd.DataFrame:
    frame = market_history.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=False).dt.tz_localize(None).dt.normalize()
    if start_date is not None:
        effective_start = pd.Timestamp(start_date) - pd.tseries.offsets.BDay(max(int(lookback_days), 0))
        frame = frame[frame["date"] >= effective_start]
    if end_date is not None:
        frame = frame[frame["date"] <= pd.Timestamp(end_date)]
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def _metrics_to_backtest_result(
    *,
    strategy_profile: str,
    params: Mapping[str, Any],
    metrics: Mapping[str, Any],
    start_date: date | None,
    end_date: date | None,
    run_duration_seconds: float,
) -> Any:
    if BacktestResult is None:
        raise ImportError("quant_platform_kit is required to build BacktestResult")
    days = int(metrics.get("days") or 0)
    annual_return = float(metrics.get("annual_return") or 0.0)
    max_drawdown = float(metrics.get("max_drawdown") or 0.0)
    annual_vol = float(metrics.get("annual_volatility") or 0.0)
    sharpe = float(metrics.get("sharpe_ratio") or 0.0)
    total_return = float(metrics.get("total_return") or 0.0)
    calmar = abs(annual_return / max_drawdown) if max_drawdown else None
    return BacktestResult(
        strategy_profile=strategy_profile,
        domain="cn_equity",
        param_set_id="",
        params=dict(params),
        sharpe_ratio=sharpe,
        calmar_ratio=calmar,
        max_drawdown=max_drawdown,
        cagr=annual_return,
        volatility=annual_vol,
        total_return=total_return,
        start_date=start_date,
        end_date=end_date,
        observation_count=days,
        source_script="cn_equity_strategies.backtest.orchestrator_runner",
        computed_at=datetime.now(timezone.utc).isoformat(),
        run_duration_seconds=run_duration_seconds,
    )


class CnProxyBacktestRunner:
    """Protocol-compatible BacktestRunner for CN ETF proxy strategies."""

    def __init__(
        self,
        *,
        market_history: pd.DataFrame | None = None,
        initial_cash: float = 1_000_000.0,
        synthetic_days: int = 500,
    ) -> None:
        self._market_history = market_history
        self._initial_cash = float(initial_cash)
        self._synthetic_days = int(synthetic_days)

    def run(
        self,
        strategy_profile: str,
        params: Mapping[str, Any],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Any:
        spec = PROXY_PROFILE_REGISTRY.get(strategy_profile)
        if spec is None:
            raise ValueError(
                f"Unsupported strategy_profile={strategy_profile!r}; "
                f"supported={sorted(SUPPORTED_PROFILES)}"
            )

        min_history_days = int(params.get("min_history_days", spec.default_min_history_days))
        history = self._market_history
        if history is None:
            history = _synthetic_market_history(
                extract_managed_symbols=spec.extract_managed_symbols,
                days=max(self._synthetic_days, min_history_days + 400),
            )
        sliced = _slice_history(
            history,
            start_date=start_date,
            end_date=end_date,
            lookback_days=min_history_days + 5,
        )
        if sliced.empty:
            raise ValueError("No market history rows for requested window")

        def _signal_fn(history_frame: Any, **kwargs: Any):
            return spec.build_target_weights(history_frame, **kwargs)

        started = datetime.now(timezone.utc)
        result = run_proxy_backtest(
            sliced,
            _signal_fn,
            config=ProxyBacktestConfig(
                initial_cash=self._initial_cash,
                min_history_days=min_history_days,
            ),
            strategy_kwargs={"min_history_days": min_history_days},
        )
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        eval_frame = sliced
        if start_date is not None:
            eval_frame = sliced[sliced["date"] >= pd.Timestamp(start_date)]
        return _metrics_to_backtest_result(
            strategy_profile=strategy_profile,
            params=params,
            metrics=result.metrics,
            start_date=start_date or (eval_frame["date"].min().date() if not eval_frame.empty else None),
            end_date=end_date or (eval_frame["date"].max().date() if not eval_frame.empty else None),
            run_duration_seconds=elapsed,
        )


__all__ = [
    "SUPPORTED_PROFILES",
    "CnProxyBacktestRunner",
]
