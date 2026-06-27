from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import pandas as pd

from cn_equity_strategies.strategies import etf_rotation_core as base

CN_EQUITY_DOMAIN = base.CN_EQUITY_DOMAIN
SIGNAL_SOURCE = "daily_market_history"
STATUS_ICON = "🇨🇳"
PROFILE_NAME = "cn_industry_etf_rotation"

# Pure A-share industry / theme ETFs (no QDII / gold / broad global beta).
INDUSTRY_THEME_SYMBOLS = (
    "159819",  # AI
    "159995",  # Chip
    "512760",  # Semiconductor
    "159994",  # Communication
    "159852",  # Software
    "512170",  # Healthcare
    "515030",  # New energy
    "159792",  # HK-connect internet (A-share sentiment spillover)
    "512800",  # Banks
    "512690",  # Liquor
    "159928",  # Consumer
)

# Optional growth/style sleeves kept domestic.
INDUSTRY_STYLE_SYMBOLS = (
    "159915",  # ChiNext
    "588000",  # STAR50
    "512100",  # CSI1000
)

DEFAULT_UNIVERSE_SYMBOLS = tuple(dict.fromkeys([*INDUSTRY_THEME_SYMBOLS, *INDUSTRY_STYLE_SYMBOLS]))
DEFAULT_DEFENSIVE_SYMBOLS = base.DEFAULT_DEFENSIVE_SYMBOLS
DEFAULT_BENCHMARK_SYMBOL = base.DEFAULT_BENCHMARK_SYMBOL

DEFAULT_MOMENTUM_WINDOW_DAYS = 60
DEFAULT_TREND_WINDOW_DAYS = 200
DEFAULT_BENCHMARK_TREND_WINDOW_DAYS = 200
DEFAULT_VOLATILITY_WINDOW_DAYS = 63
DEFAULT_TOP_N = 5
DEFAULT_MIN_MOMENTUM = 0.0
DEFAULT_REBALANCE_FREQUENCY = "monthly"
DEFAULT_WEIGHTING_MODE = base.DEFAULT_WEIGHTING_MODE
DEFAULT_TARGET_ANNUAL_VOLATILITY: float | None = 0.20
DEFAULT_MAX_GROSS_EXPOSURE = 1.0
DEFAULT_MIN_HISTORY_DAYS = 220
DEFAULT_MAX_PAIR_CORRELATION = 0.85
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = 0.02
DEFAULT_ENABLE_BENCHMARK_RISK_OFF = False

SentimentMode = Literal["off", "flow", "flow_crowding"]

DEFAULT_SENTIMENT_MODE: SentimentMode = "off"
DEFAULT_SENTIMENT_LOOKBACK_SHORT = 5
DEFAULT_SENTIMENT_LOOKBACK_LONG = 60
DEFAULT_SENTIMENT_WEIGHT = 0.15
DEFAULT_CROWDING_ZSCORE_THRESHOLD = 1.5
DEFAULT_CROWDING_PENALTY = 0.25

normalize_symbol = base.normalize_symbol
normalize_universe_symbols = base.normalize_universe_symbols
build_close_matrix = base.build_close_matrix


def _history_to_frame(market_history: Any) -> pd.DataFrame:
    if isinstance(market_history, pd.DataFrame):
        frame = market_history.copy()
    else:
        frame = pd.DataFrame(list(market_history))
    if "date" not in frame.columns:
        raise ValueError("market_history requires date column for industry sentiment scoring")
    frame["date"] = pd.to_datetime(frame["date"], utc=False).dt.tz_localize(None).dt.normalize()
    frame["symbol"] = frame["symbol"].map(normalize_symbol)
    return frame.sort_values(["date", "symbol"]).reset_index(drop=True)


def _volume_column(frame: pd.DataFrame) -> str | None:
    for column in ("volume", "turnover", "amount", "成交额", "成交量"):
        if column in frame.columns:
            return column
    return None


def _zscore(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    std = float(numeric.std(ddof=0))
    if pd.isna(std) or std == 0.0:
        return pd.Series(0.0, index=values.index, dtype=float)
    return ((numeric - numeric.mean()) / std).fillna(0.0)


def compute_turnover_surge_scores(
    market_history: Any,
    *,
    universe_symbols: Sequence[str],
    short_window: int = DEFAULT_SENTIMENT_LOOKBACK_SHORT,
    long_window: int = DEFAULT_SENTIMENT_LOOKBACK_LONG,
) -> dict[str, float]:
    frame = _history_to_frame(market_history)
    volume_column = _volume_column(frame)
    if volume_column is None:
        return {}
    symbols = normalize_universe_symbols(universe_symbols)
    volume = (
        frame.loc[frame["symbol"].isin(symbols), ["date", "symbol", volume_column]]
        .pivot_table(index="date", columns="symbol", values=volume_column, aggfunc="last")
        .sort_index()
    )
    if volume.empty or len(volume) < max(int(long_window), int(short_window)) + 1:
        return {}
    short_mean = volume.tail(int(short_window)).mean()
    long_mean = volume.tail(int(long_window)).mean().replace(0.0, pd.NA)
    surge = (short_mean / long_mean).fillna(1.0)
    zscores = _zscore(surge)
    return {str(symbol): float(zscores.get(symbol, 0.0)) for symbol in zscores.index}


def apply_sentiment_adjustment(
    rows: list[dict[str, object]],
    *,
    turnover_zscores: Mapping[str, float],
    sentiment_mode: SentimentMode,
    sentiment_weight: float,
    crowding_zscore_threshold: float,
    crowding_penalty: float,
) -> list[dict[str, object]]:
    if sentiment_mode == "off" or not turnover_zscores:
        return rows
    adjusted: list[dict[str, object]] = []
    for row in rows:
        symbol = str(row["symbol"])
        score = float(row["score"])
        turnover_z = float(turnover_zscores.get(symbol, 0.0))
        if sentiment_mode in {"flow", "flow_crowding"}:
            score *= 1.0 + float(sentiment_weight) * turnover_z
        if sentiment_mode == "flow_crowding" and turnover_z >= float(crowding_zscore_threshold):
            score *= max(0.0, 1.0 - float(crowding_penalty))
        updated = dict(row)
        updated["score"] = score
        updated["turnover_zscore"] = turnover_z
        adjusted.append(updated)
    return adjusted


def compute_latest_signal(
    market_history: Any,
    *,
    universe_symbols: Sequence[Any] | None = None,
    defensive_symbols: Sequence[Any] | None = None,
    benchmark_symbol: str | None = DEFAULT_BENCHMARK_SYMBOL,
    enable_benchmark_risk_off: bool = DEFAULT_ENABLE_BENCHMARK_RISK_OFF,
    momentum_window_days: int = DEFAULT_MOMENTUM_WINDOW_DAYS,
    trend_window_days: int = DEFAULT_TREND_WINDOW_DAYS,
    benchmark_trend_window_days: int = DEFAULT_BENCHMARK_TREND_WINDOW_DAYS,
    volatility_window_days: int = DEFAULT_VOLATILITY_WINDOW_DAYS,
    top_n: int = DEFAULT_TOP_N,
    min_momentum: float = DEFAULT_MIN_MOMENTUM,
    weighting_mode: str = DEFAULT_WEIGHTING_MODE,
    target_annual_volatility: float | None = DEFAULT_TARGET_ANNUAL_VOLATILITY,
    max_gross_exposure: float = DEFAULT_MAX_GROSS_EXPOSURE,
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS,
    max_pair_correlation: float = DEFAULT_MAX_PAIR_CORRELATION,
    sentiment_mode: SentimentMode = DEFAULT_SENTIMENT_MODE,
    sentiment_weight: float = DEFAULT_SENTIMENT_WEIGHT,
    crowding_zscore_threshold: float = DEFAULT_CROWDING_ZSCORE_THRESHOLD,
    crowding_penalty: float = DEFAULT_CROWDING_PENALTY,
) -> dict[str, object]:
    offensive = normalize_universe_symbols(universe_symbols or DEFAULT_UNIVERSE_SYMBOLS)
    if defensive_symbols is None:
        defensive = normalize_universe_symbols(DEFAULT_DEFENSIVE_SYMBOLS)
    elif defensive_symbols:
        defensive = normalize_universe_symbols(defensive_symbols)
    else:
        defensive = ()
    benchmark = normalize_symbol(benchmark_symbol) if benchmark_symbol else None
    if not enable_benchmark_risk_off:
        benchmark = None

    signal = base.compute_latest_signal(
        market_history,
        universe_symbols=offensive,
        defensive_symbols=defensive,
        benchmark_symbol=benchmark,
        momentum_window_days=int(momentum_window_days),
        trend_window_days=int(trend_window_days),
        benchmark_trend_window_days=int(benchmark_trend_window_days),
        volatility_window_days=int(volatility_window_days),
        top_n=int(top_n),
        min_momentum=float(min_momentum),
        weighting_mode=weighting_mode,
        target_annual_volatility=target_annual_volatility,
        max_gross_exposure=float(max_gross_exposure),
        min_history_days=int(min_history_days),
        max_pair_correlation=float(max_pair_correlation),
    )
    if sentiment_mode == "off":
        signal["sentiment_mode"] = sentiment_mode
        return signal

    turnover_zscores = compute_turnover_surge_scores(
        market_history,
        universe_symbols=offensive,
    )
    if not turnover_zscores:
        signal["sentiment_mode"] = "off"
        signal["sentiment_fallback"] = "missing_volume_column"
        return signal

    ranking = list(signal.get("ranking") or [])
    if not ranking:
        signal["sentiment_mode"] = sentiment_mode
        return signal

    eligible_rows = [row for row in ranking if row.get("eligible")]
    adjusted = apply_sentiment_adjustment(
        eligible_rows,
        turnover_zscores=turnover_zscores,
        sentiment_mode=sentiment_mode,
        sentiment_weight=float(sentiment_weight),
        crowding_zscore_threshold=float(crowding_zscore_threshold),
        crowding_penalty=float(crowding_penalty),
    )
    close = base.build_close_matrix(
        market_history,
        universe_symbols=offensive,
        extra_symbols=[*(defensive or ()), *( [benchmark] if benchmark else [])],
    )
    returns = close.pct_change().fillna(0.0)

    adjusted.sort(
        key=lambda row: float(row["score"]) if not signal.get("benchmark_risk_off") else -float(row.get("volatility", 0.0)),
        reverse=not bool(signal.get("benchmark_risk_off")),
    )
    if not signal.get("benchmark_risk_off"):
        selected = base._filter_ranked_by_correlation(
            adjusted,
            returns,
            top_n=int(top_n),
            max_pair_correlation=float(max_pair_correlation),
        )
    else:
        selected = adjusted[: min(int(top_n), len(adjusted))]

    weights, realized_portfolio_volatility = base._build_weights_from_ranked_rows(
        selected,
        returns=returns,
        weighting_mode=weighting_mode,
        volatility_window_days=int(volatility_window_days),
        target_annual_volatility=target_annual_volatility,
        max_gross_exposure=float(max_gross_exposure),
    )
    cash_weight = max(0.0, 1.0 - sum(weights.values()))
    signal.update(
        {
            "ranking": tuple(ranking),
            "selected_symbols": tuple(weights),
            "weights": weights,
            "cash_weight": cash_weight,
            "gross_exposure": sum(weights.values()),
            "realized_portfolio_volatility": float(realized_portfolio_volatility),
            "sentiment_mode": sentiment_mode,
            "turnover_zscores": turnover_zscores,
        }
    )
    return signal


def build_target_weights(market_history: Any, **kwargs: Any) -> tuple[dict[str, float], dict[str, object]]:
    signal = compute_latest_signal(market_history, **kwargs)
    return dict(signal["weights"]), signal


def extract_managed_symbols(*_args: Any, **kwargs: Any) -> tuple[str, ...]:
    offensive = normalize_universe_symbols(kwargs.get("universe_symbols") or DEFAULT_UNIVERSE_SYMBOLS)
    defensive_raw = kwargs.get("defensive_symbols", DEFAULT_DEFENSIVE_SYMBOLS)
    if defensive_raw is None:
        defensive = normalize_universe_symbols(DEFAULT_DEFENSIVE_SYMBOLS)
    elif defensive_raw:
        defensive = normalize_universe_symbols(defensive_raw)
    else:
        defensive = ()
    return tuple(dict.fromkeys([*offensive, *defensive]))


def compute_signals(market_history: Any, _current_holdings: Any = None, **kwargs: Any):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)
    kwargs.pop("rebalance_frequency", None)
    weights, metadata = build_target_weights(market_history, **kwargs)
    selected = ",".join(weights) if weights else "cash"
    signal_desc = (
        f"cn industry etf rotation state={metadata['signal_state']} sentiment={metadata.get('sentiment_mode')} "
        f"selected={selected} gross={metadata['gross_exposure']:.0%} cash={metadata['cash_weight']:.0%}"
    )
    status_desc = (
        f"state={metadata['signal_state']} | sentiment={metadata.get('sentiment_mode')} | "
        f"selected={selected} | top_n={metadata['top_n']}"
    )
    return (
        weights,
        signal_desc,
        bool(metadata["cash_weight"] > 1e-12),
        status_desc,
        {
            **metadata,
            "managed_symbols": extract_managed_symbols(**kwargs),
            "status_icon": STATUS_ICON,
            "signal_source": SIGNAL_SOURCE,
            "actionable": True,
        },
    )
