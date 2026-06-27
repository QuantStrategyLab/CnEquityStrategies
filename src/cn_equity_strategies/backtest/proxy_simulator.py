from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from quant_platform_kit.common.cn_equity_calendar import (
    add_cn_equity_trading_days,
    is_cn_equity_trading_day,
)

from cn_equity_strategies.strategies.etf_rotation_core import build_close_matrix, normalize_symbol

StrategySignalFn = Callable[[Any], tuple[Mapping[str, float], Mapping[str, object]]]


@dataclass(frozen=True)
class ProxyBacktestConfig:
    initial_cash: float = 1_000_000.0
    lot_size: int = 100
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    limit_pct: float = 0.10
    cash_reserve_ratio: float = 0.02
    rebalance_frequency: str = "monthly"
    min_history_days: int = 220


@dataclass
class ProxyBacktestResult:
    equity_curve: pd.Series
    daily_returns: pd.Series
    rebalance_events: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)
    final_holdings: dict[str, int] = field(default_factory=dict)
    final_cash: float = 0.0


def _commission(notional: float, *, rate: float, minimum: float) -> float:
    if notional <= 0.0:
        return 0.0
    return max(float(notional) * float(rate), float(minimum))


def _round_lot(shares: float, lot_size: int) -> int:
    if shares <= 0.0:
        return 0
    return int(shares // int(lot_size)) * int(lot_size)


def _limit_status(prev_close: float, close: float, limit_pct: float) -> str:
    if prev_close <= 0.0 or not math.isfinite(prev_close) or not math.isfinite(close):
        return "normal"
    change = float(close) / float(prev_close) - 1.0
    if change >= float(limit_pct) - 1e-9:
        return "limit_up"
    if change <= -float(limit_pct) + 1e-9:
        return "limit_down"
    return "normal"


def _history_slice(market_history: Any, as_of: pd.Timestamp) -> Any:
    if isinstance(market_history, pd.DataFrame):
        frame = market_history.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=False).dt.tz_localize(None).dt.normalize()
        return frame.loc[frame["date"] <= as_of]
    raise TypeError("proxy backtest currently requires market_history as a DataFrame")


def _rebalance_dates_from_index(index: pd.DatetimeIndex, *, frequency: str) -> list[pd.Timestamp]:
    if frequency == "monthly":
        normalized = pd.Series(index).dt.normalize()
        grouped = normalized.groupby([normalized.dt.year, normalized.dt.month]).max()
        output: list[pd.Timestamp] = []
        for value in grouped.sort_index():
            day = pd.Timestamp(value).date()
            if is_cn_equity_trading_day(day):
                output.append(pd.Timestamp(value))
        return output
    if frequency == "biweekly":
        output: list[pd.Timestamp] = []
        last_index: int | None = None
        for position, value in enumerate(index):
            if last_index is None or position - last_index >= 10:
                output.append(pd.Timestamp(value))
                last_index = position
        return output
    raise ValueError("rebalance_frequency must be 'monthly' or 'biweekly'")


def _portfolio_value(
    *,
    cash: float,
    holdings: Mapping[str, int],
    prices: Mapping[str, float],
) -> float:
    equity = float(cash)
    for symbol, quantity in holdings.items():
        price = prices.get(symbol)
        if price is None or quantity <= 0:
            continue
        equity += float(quantity) * float(price)
    return equity


def compute_backtest_metrics(daily_returns: pd.Series) -> dict[str, float | int]:
    returns = daily_returns.dropna()
    if returns.empty:
        return {
            "days": 0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "annual_volatility": 0.0,
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
        }
    equity = (1.0 + returns).cumprod()
    years = len(returns) / 252.0
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    annual_volatility = float(returns.std(ddof=0) * math.sqrt(252))
    sharpe = annual_return / annual_volatility if annual_volatility > 0 else 0.0
    return {
        "days": int(len(returns)),
        "annual_return": annual_return,
        "max_drawdown": float(drawdown.min()),
        "annual_volatility": annual_volatility,
        "total_return": float(equity.iloc[-1] - 1.0),
        "sharpe_ratio": float(sharpe),
    }


def run_proxy_backtest(
    market_history: Any,
    strategy_signal_fn: StrategySignalFn,
    *,
    config: ProxyBacktestConfig | None = None,
    universe_symbols: Sequence[str] | None = None,
    strategy_kwargs: Mapping[str, Any] | None = None,
) -> ProxyBacktestResult:
    settings = config or ProxyBacktestConfig()
    kwargs = dict(strategy_kwargs or {})
    if universe_symbols is None and isinstance(market_history, pd.DataFrame):
        universe_symbols = tuple(
            dict.fromkeys(market_history["symbol"].map(normalize_symbol).tolist()),
        )
    close = build_close_matrix(market_history, universe_symbols=universe_symbols)
    if len(close) < int(settings.min_history_days):
        raise ValueError(
            f"market_history requires at least {int(settings.min_history_days)} overlapping trading days"
        )

    index = pd.DatetimeIndex(close.index)
    rebalance_dates = _rebalance_dates_from_index(index, frequency=settings.rebalance_frequency)
    if not rebalance_dates:
        raise ValueError("no rebalance dates found in market history")

    cash = float(settings.initial_cash)
    holdings: dict[str, int] = {}
    locked: dict[str, int] = {}
    pending_targets: dict[str, float] | None = None
    pending_signal_day: pd.Timestamp | None = None
    pending_metadata: dict[str, object] = {}
    rebalance_events: list[dict[str, object]] = []
    equity_points: dict[pd.Timestamp, float] = {}

    for day in index:
        day_ts = pd.Timestamp(day)
        prices = {symbol: float(close.loc[day_ts, symbol]) for symbol in close.columns}
        prev_day_pos = index.get_loc(day_ts) - 1
        prev_prices = (
            {symbol: float(close.iloc[prev_day_pos][symbol]) for symbol in close.columns}
            if prev_day_pos >= 0
            else prices
        )

        locked.clear()

        execution_due = False
        if pending_targets is not None and pending_signal_day is not None:
            execution_day = pd.Timestamp(add_cn_equity_trading_days(pending_signal_day.date(), 1))
            execution_due = day_ts >= execution_day
        if execution_due and pending_targets is not None:
            portfolio_value = _portfolio_value(cash=cash, holdings=holdings, prices=prices)
            investable = portfolio_value * (1.0 - float(settings.cash_reserve_ratio))
            target_values = {
                normalize_symbol(symbol): investable * float(weight)
                for symbol, weight in pending_targets.items()
                if float(weight) > 0.0
            }
            all_symbols = sorted(set(holdings) | set(target_values) | set(close.columns))
            trades: list[dict[str, object]] = []

            for symbol in all_symbols:
                price = prices.get(symbol)
                if price is None or price <= 0.0:
                    continue
                current_qty = int(holdings.get(symbol, 0))
                sellable_qty = max(current_qty - int(locked.get(symbol, 0)), 0)
                target_qty = _round_lot(target_values.get(symbol, 0.0) / price, settings.lot_size)
                delta = target_qty - current_qty
                if delta == 0:
                    continue
                limit = _limit_status(prev_prices.get(symbol, price), price, settings.limit_pct)
                if delta < 0:
                    if limit == "limit_down":
                        trades.append({"symbol": symbol, "side": "sell", "status": "blocked_limit_down", "qty": 0})
                        continue
                    sell_qty = min(-delta, sellable_qty)
                    sell_qty = _round_lot(sell_qty, settings.lot_size)
                    if sell_qty <= 0:
                        continue
                    notional = sell_qty * price
                    fee = _commission(notional, rate=settings.commission_rate, minimum=settings.min_commission)
                    cash += notional - fee
                    holdings[symbol] = current_qty - sell_qty
                    if holdings[symbol] <= 0:
                        holdings.pop(symbol, None)
                    trades.append(
                        {
                            "symbol": symbol,
                            "side": "sell",
                            "status": "filled",
                            "qty": sell_qty,
                            "price": price,
                            "fee": fee,
                        }
                    )

            for symbol in all_symbols:
                price = prices.get(symbol)
                if price is None or price <= 0.0:
                    continue
                current_qty = int(holdings.get(symbol, 0))
                target_qty = _round_lot(target_values.get(symbol, 0.0) / price, settings.lot_size)
                delta = target_qty - current_qty
                if delta <= 0:
                    continue
                limit = _limit_status(prev_prices.get(symbol, price), price, settings.limit_pct)
                if limit == "limit_up":
                    trades.append({"symbol": symbol, "side": "buy", "status": "blocked_limit_up", "qty": 0})
                    continue
                buy_qty = _round_lot(delta, settings.lot_size)
                if buy_qty <= 0:
                    continue
                notional = buy_qty * price
                fee = _commission(notional, rate=settings.commission_rate, minimum=settings.min_commission)
                total_cost = notional + fee
                if total_cost > cash:
                    affordable_qty = _round_lot(max(cash - fee, 0.0) / price, settings.lot_size)
                    if affordable_qty <= 0:
                        trades.append({"symbol": symbol, "side": "buy", "status": "blocked_insufficient_cash", "qty": 0})
                        continue
                    buy_qty = affordable_qty
                    notional = buy_qty * price
                    fee = _commission(notional, rate=settings.commission_rate, minimum=settings.min_commission)
                    total_cost = notional + fee
                cash -= total_cost
                holdings[symbol] = current_qty + buy_qty
                locked[symbol] = int(locked.get(symbol, 0)) + buy_qty
                trades.append(
                    {
                        "symbol": symbol,
                        "side": "buy",
                        "status": "filled",
                        "qty": buy_qty,
                        "price": price,
                        "fee": fee,
                    }
                )

            rebalance_events.append(
                {
                    "signal_date": pending_signal_day.date().isoformat(),
                    "execution_date": day_ts.date().isoformat(),
                    "targets": dict(pending_targets),
                    "metadata": dict(pending_metadata),
                    "trades": trades,
                    "portfolio_value_after": _portfolio_value(cash=cash, holdings=holdings, prices=prices),
                }
            )
            pending_targets = None
            pending_signal_day = None
            pending_metadata = {}

        if day_ts in rebalance_dates and day_ts >= index[settings.min_history_days - 1]:
            history = _history_slice(market_history, day_ts)
            weights, metadata = strategy_signal_fn(history, **kwargs)
            pending_targets = {normalize_symbol(symbol): float(value) for symbol, value in weights.items()}
            pending_signal_day = day_ts
            pending_metadata = dict(metadata)

        equity_points[day_ts] = _portfolio_value(cash=cash, holdings=holdings, prices=prices)

    equity_curve = pd.Series(equity_points).sort_index()
    daily_returns = equity_curve.pct_change().fillna(0.0)
    metrics = compute_backtest_metrics(daily_returns)
    return ProxyBacktestResult(
        equity_curve=equity_curve,
        daily_returns=daily_returns,
        rebalance_events=rebalance_events,
        metrics=metrics,
        final_holdings=dict(holdings),
        final_cash=cash,
    )


__all__ = [
    "ProxyBacktestConfig",
    "ProxyBacktestResult",
    "StrategySignalFn",
    "compute_backtest_metrics",
    "run_proxy_backtest",
]
