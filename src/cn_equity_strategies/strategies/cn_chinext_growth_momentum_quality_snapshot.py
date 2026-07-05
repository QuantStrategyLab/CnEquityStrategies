from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

CN_EQUITY_DOMAIN = "cn_equity"
SIGNAL_SOURCE = "factor_snapshot"
STATUS_ICON = "🇨🇳"
PROFILE_NAME = "cn_chinext_growth_momentum_quality_snapshot"
SAFE_HAVEN = "511880"
SNAPSHOT_CONTRACT_VERSION = "cn_chinext_growth_momentum_quality_snapshot.factor_snapshot.v1"

DEFAULT_HOLDINGS_COUNT = 12
DEFAULT_SINGLE_NAME_CAP = 0.10
DEFAULT_SECTOR_CAP = 0.35
DEFAULT_MIN_ADV20_CNY = 20_000_000.0
DEFAULT_MIN_MARKET_CAP_CNY = 2_000_000_000.0
DEFAULT_MIN_MARKET_CAP_PERCENTILE = 0.70
DEFAULT_MIN_REVENUE_YOY = -0.05
DEFAULT_MIN_PROFIT_YOY = -0.20
DEFAULT_MIN_MOMENTUM = -0.05
DEFAULT_MIN_LIST_DAYS = 252
DEFAULT_HOLD_BUFFER = 1
DEFAULT_HOLD_BONUS = 0.02
DEFAULT_RISK_ON_EXPOSURE = 1.0
DEFAULT_SOFT_DEFENSE_EXPOSURE = 0.75
DEFAULT_HARD_DEFENSE_EXPOSURE = 0.35
DEFAULT_SOFT_BREADTH_THRESHOLD = 0.50
DEFAULT_HARD_BREADTH_THRESHOLD = 0.30
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = 0.02

REQUIRED_FACTOR_COLUMNS = frozenset(
    {
        "symbol",
        "sector",
        "close_cny",
        "adv20_cny",
        "market_cap_cny",
        "revenue_yoy",
        "profit_yoy",
        "revenue_acceleration_2q",
        "roe_ttm",
        "roe_stability_3y",
        "gross_margin_stability_3y",
        "mom_12_1",
        "mom_6_1",
        "sma200_gap",
        "realized_vol_126",
        "earnings_positive",
        "suspension_days_63",
        "is_st",
        "list_days",
    }
)
DEFAULT_ADV20_CNY_UNIT_SCALE = 10_000.0
DEFAULT_ADV20_CNY_UNIT_SCALE_THRESHOLD = 10_000_000.0


def _coerce_bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() else text


def _normalize_holdings(current_holdings: Any) -> set[str]:
    if current_holdings is None:
        return set()
    raw_symbols = current_holdings.keys() if isinstance(current_holdings, Mapping) else current_holdings
    normalized: set[str] = set()
    for item in raw_symbols:
        symbol = getattr(item, "symbol", item)
        symbol_text = normalize_symbol(symbol)
        if symbol_text:
            normalized.add(symbol_text)
    return normalized


def _to_frame(factor_snapshot: Any) -> pd.DataFrame:
    frame = factor_snapshot.copy() if isinstance(factor_snapshot, pd.DataFrame) else pd.DataFrame(list(factor_snapshot))
    if frame.empty:
        raise ValueError("factor_snapshot must contain at least one row")

    missing = REQUIRED_FACTOR_COLUMNS - set(frame.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"factor_snapshot missing required columns: {missing_text}")

    frame["symbol"] = frame["symbol"].map(normalize_symbol)
    frame["sector"] = frame["sector"].fillna("unknown").astype(str).str.strip().replace("", "unknown")
    frame["earnings_positive"] = frame["earnings_positive"].map(_coerce_bool)
    frame["is_st"] = frame["is_st"].map(_coerce_bool)
    numeric_columns = REQUIRED_FACTOR_COLUMNS - {"symbol", "sector", "earnings_positive", "is_st"}
    for column in sorted(numeric_columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    adv20_median = float(frame["adv20_cny"].dropna().median()) if "adv20_cny" in frame.columns else 0.0
    if 0.0 < adv20_median < float(DEFAULT_ADV20_CNY_UNIT_SCALE_THRESHOLD):
        frame["adv20_cny"] = frame["adv20_cny"] * float(DEFAULT_ADV20_CNY_UNIT_SCALE)
    return frame


def _zscore(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    std = float(numeric.std(ddof=0))
    if pd.isna(std) or std == 0.0:
        return pd.Series(0.0, index=values.index, dtype=float)
    return ((numeric - numeric.mean()) / std).fillna(0.0)


def _sector_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    return frame.groupby("sector")[column].transform(_zscore).fillna(0.0)


def _candidate_frame(
    frame: pd.DataFrame,
    *,
    safe_haven: str,
    min_adv20_cny: float,
    min_market_cap_cny: float,
    min_revenue_yoy: float,
    min_profit_yoy: float,
    min_momentum: float,
    min_list_days: int,
) -> pd.DataFrame:
    safe_haven = normalize_symbol(safe_haven)
    return frame.loc[
        (frame["symbol"] != safe_haven)
        & ~frame["is_st"]
        & frame["adv20_cny"].ge(float(min_adv20_cny))
        & frame["market_cap_cny"].ge(float(min_market_cap_cny))
        & frame["revenue_yoy"].ge(float(min_revenue_yoy))
        & frame["profit_yoy"].ge(float(min_profit_yoy))
        & frame["mom_12_1"].ge(float(min_momentum))
        & frame["list_days"].ge(int(min_list_days))
        & frame[
            [
                "adv20_cny",
                "market_cap_cny",
                "revenue_yoy",
                "profit_yoy",
                "revenue_acceleration_2q",
                "roe_ttm",
                "roe_stability_3y",
                "gross_margin_stability_3y",
                "mom_12_1",
                "mom_6_1",
                "sma200_gap",
                "realized_vol_126",
                "list_days",
            ]
        ]
        .notna()
        .all(axis=1)
    ].copy()


def score_candidates(
    factor_snapshot: Any,
    current_holdings: Iterable[str] | None = None,
    *,
    safe_haven: str = SAFE_HAVEN,
    min_adv20_cny: float = DEFAULT_MIN_ADV20_CNY,
    min_market_cap_cny: float = DEFAULT_MIN_MARKET_CAP_CNY,
    min_revenue_yoy: float = DEFAULT_MIN_REVENUE_YOY,
    min_profit_yoy: float = DEFAULT_MIN_PROFIT_YOY,
    min_momentum: float = DEFAULT_MIN_MOMENTUM,
    min_list_days: int = DEFAULT_MIN_LIST_DAYS,
    hold_bonus: float = DEFAULT_HOLD_BONUS,
) -> pd.DataFrame:
    frame = _to_frame(factor_snapshot)
    eligible = _candidate_frame(
        frame,
        safe_haven=safe_haven,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
        min_revenue_yoy=float(min_revenue_yoy),
        min_profit_yoy=float(min_profit_yoy),
        min_momentum=float(min_momentum),
        min_list_days=int(min_list_days),
    )
    if eligible.empty:
        return pd.DataFrame(columns=["rank", "symbol", "sector", "score", "eligible"])

    market_cap_floor = float(eligible["market_cap_cny"].quantile(float(DEFAULT_MIN_MARKET_CAP_PERCENTILE)))
    if math.isfinite(market_cap_floor):
        trimmed = eligible.loc[eligible["market_cap_cny"].ge(market_cap_floor)].copy()
        if len(trimmed) >= 5:
            eligible = trimmed

    growth_score = (
        _sector_zscore(eligible, "revenue_yoy") * 0.40
        + _sector_zscore(eligible, "profit_yoy") * 0.35
        + _sector_zscore(eligible, "revenue_acceleration_2q") * 0.25
    )
    momentum_score = (
        _zscore(eligible["mom_12_1"]) * 0.50
        + _zscore(eligible["mom_6_1"]) * 0.30
        + _zscore(eligible["sma200_gap"]) * 0.20
    )
    liquidity_score = _zscore(pd.to_numeric(eligible["adv20_cny"], errors="coerce").clip(lower=1.0).map(math.log10))
    risk_penalty = _zscore(eligible["realized_vol_126"])
    earnings_bonus = eligible["earnings_positive"].astype(float) * 0.05
    eligible["score"] = (
        growth_score * 0.50
        + momentum_score * 0.40
        + liquidity_score * 0.10
        + earnings_bonus
        - risk_penalty * 0.05
    )
    current_holdings_set = _normalize_holdings(current_holdings)
    if current_holdings_set:
        eligible.loc[eligible["symbol"].isin(current_holdings_set), "score"] += float(hold_bonus)

    ranked = eligible.sort_values(
        by=["score", "revenue_yoy", "mom_12_1", "market_cap_cny", "symbol"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    ranked["eligible"] = True
    return ranked.loc[
        :,
        [
            "rank",
            "symbol",
            "sector",
            "score",
            "eligible",
            "close_cny",
            "adv20_cny",
            "market_cap_cny",
            "revenue_yoy",
            "profit_yoy",
            "revenue_acceleration_2q",
            "roe_ttm",
            "roe_stability_3y",
            "gross_margin_stability_3y",
            "mom_12_1",
            "mom_6_1",
            "sma200_gap",
            "realized_vol_126",
        ],
    ]


def _resolve_stock_exposure(
    frame: pd.DataFrame,
    *,
    safe_haven: str,
    min_adv20_cny: float,
    min_market_cap_cny: float,
    min_revenue_yoy: float,
    min_profit_yoy: float,
    min_momentum: float,
    min_list_days: int,
    risk_on_exposure: float,
    soft_defense_exposure: float,
    hard_defense_exposure: float,
    soft_breadth_threshold: float,
    hard_breadth_threshold: float,
) -> tuple[float, str, float]:
    candidates = _candidate_frame(
        frame,
        safe_haven=safe_haven,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
        min_revenue_yoy=float(min_revenue_yoy),
        min_profit_yoy=float(min_profit_yoy),
        min_momentum=float(min_momentum),
        min_list_days=int(min_list_days),
    )
    if candidates.empty:
        return float(hard_defense_exposure), "hard_defense", 0.0
    breadth_signal = (candidates["sma200_gap"] > -0.03) | (candidates["mom_12_1"] > 0.05)
    breadth_ratio = float(breadth_signal.mean())
    if breadth_ratio < float(hard_breadth_threshold):
        return float(hard_defense_exposure), "hard_defense", breadth_ratio
    if breadth_ratio < float(soft_breadth_threshold):
        return float(soft_defense_exposure), "soft_defense", breadth_ratio
    return float(risk_on_exposure), "risk_on", breadth_ratio


def _select_with_sector_cap(
    ranked: pd.DataFrame,
    *,
    holdings_count: int,
    single_name_cap: float,
    sector_cap: float,
    current_holdings: set[str],
    hold_buffer: int,
) -> list[str]:
    if ranked.empty or holdings_count <= 0:
        return []
    max_names_by_sector = max(
        1,
        int(math.floor((float(sector_cap) + 1e-12) / max(float(single_name_cap), 1e-12))),
    )
    selected: list[str] = []
    sector_counts: dict[str, int] = {}
    rank_map = dict(zip(ranked["symbol"].astype(str), ranked["rank"].astype(int)))
    sector_map = dict(zip(ranked["symbol"].astype(str), ranked["sector"].astype(str)))
    max_hold_rank = int(holdings_count) + max(int(hold_buffer), 0)

    preferred_symbols = [
        symbol
        for symbol in ranked["symbol"].astype(str).tolist()
        if symbol in current_holdings and int(rank_map[symbol]) <= max_hold_rank
    ]
    all_symbols = preferred_symbols + [symbol for symbol in ranked["symbol"].astype(str).tolist() if symbol not in preferred_symbols]
    for symbol in all_symbols:
        if len(selected) >= int(holdings_count):
            break
        sector = sector_map.get(symbol, "unknown")
        if sector_counts.get(sector, 0) >= max_names_by_sector:
            continue
        selected.append(symbol)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    return selected


def build_target_weights(
    factor_snapshot: Any,
    current_holdings: Iterable[str] | None = None,
    *,
    safe_haven: str = SAFE_HAVEN,
    holdings_count: int = DEFAULT_HOLDINGS_COUNT,
    single_name_cap: float = DEFAULT_SINGLE_NAME_CAP,
    sector_cap: float = DEFAULT_SECTOR_CAP,
    min_adv20_cny: float = DEFAULT_MIN_ADV20_CNY,
    min_market_cap_cny: float = DEFAULT_MIN_MARKET_CAP_CNY,
    min_revenue_yoy: float = DEFAULT_MIN_REVENUE_YOY,
    min_profit_yoy: float = DEFAULT_MIN_PROFIT_YOY,
    min_momentum: float = DEFAULT_MIN_MOMENTUM,
    min_list_days: int = DEFAULT_MIN_LIST_DAYS,
    hold_buffer: int = DEFAULT_HOLD_BUFFER,
    hold_bonus: float = DEFAULT_HOLD_BONUS,
    risk_on_exposure: float = DEFAULT_RISK_ON_EXPOSURE,
    soft_defense_exposure: float = DEFAULT_SOFT_DEFENSE_EXPOSURE,
    hard_defense_exposure: float = DEFAULT_HARD_DEFENSE_EXPOSURE,
    soft_breadth_threshold: float = DEFAULT_SOFT_BREADTH_THRESHOLD,
    hard_breadth_threshold: float = DEFAULT_HARD_BREADTH_THRESHOLD,
) -> tuple[dict[str, float], pd.DataFrame, dict[str, object]]:
    frame = _to_frame(factor_snapshot)
    safe_haven = normalize_symbol(safe_haven)
    stock_exposure, regime, breadth_ratio = _resolve_stock_exposure(
        frame,
        safe_haven=safe_haven,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
        min_revenue_yoy=float(min_revenue_yoy),
        min_profit_yoy=float(min_profit_yoy),
        min_momentum=float(min_momentum),
        min_list_days=int(min_list_days),
        risk_on_exposure=float(risk_on_exposure),
        soft_defense_exposure=float(soft_defense_exposure),
        hard_defense_exposure=float(hard_defense_exposure),
        soft_breadth_threshold=float(soft_breadth_threshold),
        hard_breadth_threshold=float(hard_breadth_threshold),
    )
    ranked = score_candidates(
        frame,
        current_holdings,
        safe_haven=safe_haven,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
        min_revenue_yoy=float(min_revenue_yoy),
        min_profit_yoy=float(min_profit_yoy),
        min_momentum=float(min_momentum),
        min_list_days=int(min_list_days),
        hold_bonus=float(hold_bonus),
    )
    metadata: dict[str, object] = {
        "regime": regime,
        "breadth_ratio": breadth_ratio,
        "target_stock_weight": float(stock_exposure),
        "realized_stock_weight": 0.0,
        "safe_haven_weight": 1.0,
        "selected_symbols": (),
        "selected_count": 0,
        "candidate_count": int(len(ranked)),
    }
    if ranked.empty or stock_exposure <= 0:
        return {safe_haven: 1.0}, ranked, metadata

    selected = _select_with_sector_cap(
        ranked,
        holdings_count=int(holdings_count),
        single_name_cap=float(single_name_cap),
        sector_cap=float(sector_cap),
        current_holdings=_normalize_holdings(current_holdings),
        hold_buffer=int(hold_buffer),
    )
    if not selected:
        return {safe_haven: 1.0}, ranked, metadata

    per_name_weight = min(float(single_name_cap), float(stock_exposure) / len(selected))
    weights = {symbol: float(per_name_weight) for symbol in selected}
    invested_weight = float(sum(weights.values()))
    safe_weight = max(0.0, 1.0 - invested_weight)
    if safe_weight > 1e-12:
        weights[safe_haven] = safe_weight
    metadata.update(
        {
            "realized_stock_weight": invested_weight,
            "safe_haven_weight": safe_weight,
            "selected_symbols": tuple(selected),
            "selected_count": int(len(selected)),
        }
    )
    return weights, ranked, metadata


def extract_managed_symbols(factor_snapshot: Any, *, safe_haven: str = SAFE_HAVEN, **_kwargs: Any) -> tuple[str, ...]:
    frame = _to_frame(factor_snapshot)
    safe_haven = normalize_symbol(safe_haven)
    symbols = [symbol for symbol in frame["symbol"].tolist() if symbol != safe_haven]
    if safe_haven not in symbols:
        symbols.append(safe_haven)
    return tuple(dict.fromkeys(symbols))


def compute_signals(factor_snapshot: Any, current_holdings: Any, *, safe_haven: str = SAFE_HAVEN, **kwargs: Any):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)
    weights, ranked, metadata = build_target_weights(
        factor_snapshot,
        current_holdings,
        safe_haven=safe_haven,
        **kwargs,
    )
    top_preview = ", ".join(f"{row.symbol}({row.score:.2f})" for row in ranked.head(5).itertuples(index=False))
    signal_desc = (
        f"cn chinext growth momentum quality regime={metadata['regime']} breadth={metadata['breadth_ratio']:.1%} "
        f"target_stock={metadata['target_stock_weight']:.1%} selected={metadata['selected_count']} top={top_preview}"
    )
    status_desc = (
        f"regime={metadata['regime']} | breadth={metadata['breadth_ratio']:.1%} | "
        f"target_stock={metadata['target_stock_weight']:.1%}"
    )
    return (
        weights,
        signal_desc,
        metadata["regime"] == "hard_defense",
        status_desc,
        {
            **metadata,
            "managed_symbols": extract_managed_symbols(factor_snapshot, safe_haven=safe_haven),
            "status_icon": STATUS_ICON,
            "signal_source": SIGNAL_SOURCE,
            "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
            "actionable": True,
        },
    )
