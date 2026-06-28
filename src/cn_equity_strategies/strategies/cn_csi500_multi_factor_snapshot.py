"""CSI500 multi-factor snapshot strategy — momentum + quality + low-vol.

Consumes a monthly factor snapshot (feature_snapshot) produced by the
CnEquitySnapshotPipelines CSI500 pipeline.  Multi-factor scoring mirrors
the Russell Top50 Leader Rotation approach, adapted for A-share factors.

Factor weights
--------------
mom_6_1                         0.25  — 6-month price momentum
rel_mom_6m_vs_benchmark         0.20  — relative momentum vs CSI300
mom_12_1                        0.15  — 12-1 month price momentum
sma200_gap                      0.15  — distance above 200-day MA (trend)
roe_ttm                         0.10  — trailing ROE (quality)
realized_vol_126 (inverted)     0.10  — low volatility preference
maxdd_126 (inverted)            0.05  — drawdown recovery signal

Defence
-------
Breadth-based regime switching (same as dividend_quality_snapshot):
  risk_on       breadth ≥ soft_breadth_threshold → full exposure
  soft_defense  hard_threshold ≤ breadth < soft_threshold → partial
  hard_defense  breadth < hard_threshold → safe haven only
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

CN_EQUITY_DOMAIN = "cn_equity"
SIGNAL_SOURCE = "feature_snapshot"
STATUS_ICON = "🇨🇳"
PROFILE_NAME = "cn_csi500_multi_factor_snapshot"
BENCHMARK_SYMBOL = "510300"
BROAD_BENCHMARK_SYMBOL = "510300"
SAFE_HAVEN = "510300"
DEFAULT_DYNAMIC_UNIVERSE_SIZE = 20
DEFAULT_HOLDINGS_COUNT = 10
DEFAULT_SINGLE_NAME_CAP = 0.12
DEFAULT_SECTOR_CAP = 0.30
DEFAULT_MIN_ADV20_CNY = 20_000_000.0
DEFAULT_MIN_MARKET_CAP_CNY = 3_000_000_000.0
DEFAULT_MIN_ROE_TTM = 0.0
DEFAULT_HOLD_BUFFER = 2
DEFAULT_HOLD_BONUS = 0.05
DEFAULT_RISK_ON_EXPOSURE = 1.0
DEFAULT_SOFT_DEFENSE_EXPOSURE = 0.50
DEFAULT_HARD_DEFENSE_EXPOSURE = 0.0
DEFAULT_SOFT_BREADTH_THRESHOLD = 0.40
DEFAULT_HARD_BREADTH_THRESHOLD = 0.25
DEFAULT_EXECUTION_CASH_RESERVE_RATIO = 0.02
SNAPSHOT_CONTRACT_VERSION = "cn_csi500_multi_factor_snapshot.feature_snapshot.v1"
REQUIRE_SNAPSHOT_MANIFEST = True

REQUIRED_FACTOR_COLUMNS = frozenset(
    {
        "symbol",
        "sector",
        "close",
        "adv20_cny",
        "market_cap_cny",
        "roe_ttm",
        "earnings_positive",
        "mom_6_1",
        "mom_12_1",
        "rel_mom_6m_vs_benchmark",
        "sma200_gap",
        "realized_vol_126",
        "maxdd_126",
    }
)

FEATURE_SNAPSHOT_COLUMNS = (
    "symbol",
    "sector",
    "close",
    "adv20_cny",
    "market_cap_cny",
    "roe_ttm",
    "earnings_positive",
    "mom_6_1",
    "mom_12_1",
    "rel_mom_6m_vs_benchmark",
    "sma200_gap",
    "realized_vol_126",
    "maxdd_126",
)

# Multi-factor scoring weights
FACTOR_WEIGHTS: dict[str, float] = {
    "mom_6_1": 0.25,
    "rel_mom_6m_vs_benchmark": 0.20,
    "mom_12_1": 0.15,
    "sma200_gap": 0.15,
    "roe_ttm": 0.10,
    "realized_vol_126": -0.10,
    "maxdd_126": -0.05,
}


def _coerce_bool(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y"}


def normalize_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    if text.isdigit():
        return text.zfill(6)
    return text


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


def _to_frame(feature_snapshot: Any) -> pd.DataFrame:
    frame = feature_snapshot.copy() if isinstance(feature_snapshot, pd.DataFrame) else pd.DataFrame(list(feature_snapshot))
    if frame.empty:
        raise ValueError("feature_snapshot must contain at least one row")

    missing = REQUIRED_FACTOR_COLUMNS - set(frame.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"feature_snapshot missing required columns: {missing_text}")

    frame["symbol"] = frame["symbol"].map(normalize_symbol)
    frame["sector"] = frame["sector"].fillna("unknown").astype(str).str.strip().replace("", "unknown")
    frame["earnings_positive"] = frame["earnings_positive"].map(_coerce_bool)
    numeric_columns = REQUIRED_FACTOR_COLUMNS - {"symbol", "sector", "earnings_positive"}
    for column in sorted(numeric_columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _zscore(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    std = float(numeric.std(ddof=0))
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index, dtype=float)
    return ((numeric - numeric.mean()) / std).fillna(0.0)


def _candidate_frame(
    frame: pd.DataFrame,
    *,
    min_adv20_cny: float,
    min_market_cap_cny: float,
) -> pd.DataFrame:
    excluded = {normalize_symbol(BENCHMARK_SYMBOL), normalize_symbol(BROAD_BENCHMARK_SYMBOL), normalize_symbol(SAFE_HAVEN)}
    feature_columns = list(FACTOR_WEIGHTS)
    return frame.loc[
        ~frame["symbol"].isin(excluded)
        & frame["earnings_positive"]
        & frame["adv20_cny"].ge(float(min_adv20_cny))
        & frame["market_cap_cny"].ge(float(min_market_cap_cny))
        & frame[feature_columns].notna().all(axis=1)
    ].copy()


def score_candidates(
    feature_snapshot: Any,
    current_holdings: Iterable[str] | None = None,
    *,
    min_adv20_cny: float = DEFAULT_MIN_ADV20_CNY,
    min_market_cap_cny: float = DEFAULT_MIN_MARKET_CAP_CNY,
    hold_bonus: float = DEFAULT_HOLD_BONUS,
) -> pd.DataFrame:
    frame = _to_frame(feature_snapshot)
    eligible = _candidate_frame(
        frame,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
    )
    if eligible.empty:
        return pd.DataFrame(columns=["rank", "symbol", "sector", "score", "eligible"])

    factor_columns = list(FACTOR_WEIGHTS)
    for column in factor_columns:
        eligible[f"z_{column}"] = _zscore(eligible[column])

    score = pd.Series(0.0, index=eligible.index)
    for column, weight in FACTOR_WEIGHTS.items():
        score += float(weight) * eligible[f"z_{column}"]

    eligible["score"] = score

    current_holdings_set = _normalize_holdings(current_holdings)
    if current_holdings_set:
        eligible.loc[eligible["symbol"].isin(current_holdings_set), "score"] += float(hold_bonus)

    ranked = eligible.sort_values(
        by=["score", "mom_6_1", "rel_mom_6m_vs_benchmark", "symbol"],
        ascending=[False, False, False, True],
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
            "close",
            "adv20_cny",
            "market_cap_cny",
            "roe_ttm",
            "mom_6_1",
            "mom_12_1",
            "rel_mom_6m_vs_benchmark",
            "sma200_gap",
            "realized_vol_126",
            "maxdd_126",
        ],
    ]


def _resolve_stock_exposure(
    frame: pd.DataFrame,
    *,
    min_adv20_cny: float,
    min_market_cap_cny: float,
    risk_on_exposure: float,
    soft_defense_exposure: float,
    hard_defense_exposure: float,
    soft_breadth_threshold: float,
    hard_breadth_threshold: float,
) -> tuple[float, str, float]:
    candidates = _candidate_frame(
        frame,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
    )
    breadth_ratio = float((candidates["sma200_gap"] > 0).mean()) if not candidates.empty else 0.0
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

    preferred = [
        symbol
        for symbol in ranked["symbol"].astype(str).tolist()
        if symbol in current_holdings and int(rank_map[symbol]) <= max_hold_rank
    ]
    all_symbols = preferred + [symbol for symbol in ranked["symbol"].astype(str).tolist() if symbol not in preferred]
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
    feature_snapshot: Any,
    current_holdings: Iterable[str] | None = None,
    *,
    holdings_count: int = DEFAULT_HOLDINGS_COUNT,
    single_name_cap: float = DEFAULT_SINGLE_NAME_CAP,
    sector_cap: float = DEFAULT_SECTOR_CAP,
    min_adv20_cny: float = DEFAULT_MIN_ADV20_CNY,
    min_market_cap_cny: float = DEFAULT_MIN_MARKET_CAP_CNY,
    hold_buffer: int = DEFAULT_HOLD_BUFFER,
    hold_bonus: float = DEFAULT_HOLD_BONUS,
    risk_on_exposure: float = DEFAULT_RISK_ON_EXPOSURE,
    soft_defense_exposure: float = DEFAULT_SOFT_DEFENSE_EXPOSURE,
    hard_defense_exposure: float = DEFAULT_HARD_DEFENSE_EXPOSURE,
    soft_breadth_threshold: float = DEFAULT_SOFT_BREADTH_THRESHOLD,
    hard_breadth_threshold: float = DEFAULT_HARD_BREADTH_THRESHOLD,
) -> tuple[dict[str, float], pd.DataFrame, dict[str, object]]:
    frame = _to_frame(feature_snapshot)
    safe_haven = normalize_symbol(SAFE_HAVEN)
    stock_exposure, regime, breadth_ratio = _resolve_stock_exposure(
        frame,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
        risk_on_exposure=float(risk_on_exposure),
        soft_defense_exposure=float(soft_defense_exposure),
        hard_defense_exposure=float(hard_defense_exposure),
        soft_breadth_threshold=float(soft_breadth_threshold),
        hard_breadth_threshold=float(hard_breadth_threshold),
    )
    ranked = score_candidates(
        frame,
        current_holdings,
        min_adv20_cny=float(min_adv20_cny),
        min_market_cap_cny=float(min_market_cap_cny),
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


def extract_managed_symbols(feature_snapshot: Any, **kwargs: Any) -> tuple[str, ...]:
    frame = _to_frame(feature_snapshot)
    safe_haven = normalize_symbol(SAFE_HAVEN)
    symbols = [s for s in frame["symbol"].tolist() if s != safe_haven]
    if safe_haven not in symbols:
        symbols.append(safe_haven)
    return tuple(dict.fromkeys(symbols))


def compute_signals(feature_snapshot: Any, current_holdings: Any, **kwargs: Any):
    kwargs.pop("translator", None)
    kwargs.pop("signal_text_fn", None)
    kwargs.pop("execution_cash_reserve_ratio", None)
    weights, ranked, metadata = build_target_weights(
        feature_snapshot,
        current_holdings,
        **kwargs,
    )
    top_preview = ", ".join(f"{row.symbol}({row.score:.2f})" for row in ranked.head(5).itertuples(index=False))
    signal_desc = (
        f"csi500 multi-factor regime={metadata['regime']} breadth={metadata['breadth_ratio']:.1%} "
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
            "managed_symbols": extract_managed_symbols(feature_snapshot, **kwargs),
            "status_icon": STATUS_ICON,
            "signal_source": SIGNAL_SOURCE,
            "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
            "actionable": True,
        },
    )
