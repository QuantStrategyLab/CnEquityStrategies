# CN Growth Sleeve Structure Draft (2026-07-05)

> This is a design draft for the CN growth stack. It is not a trading
> recommendation.

## Goal

Turn the CN growth side from "a few tactical or research leftovers" into a
clean structure with three first-class roles:

1. **ChiNext growth sleeve**
2. **STAR growth sleeve**
3. **CN combo orchestrator**

This is a design correction, not just a parameter tweak.

## Why the old shape was wrong

The earlier shape treated ChiNext / STAR too much like side research tracks.
That is too narrow for the current market regime.

Public market evidence shows that both growth boards can lead strongly in a
growth-led phase. The better interpretation is:

- the boards themselves are valid growth universes,
- the strategy shape needs board-specific gates,
- the combo layer should allocate sleeves, not pretend to be the only alpha.

## Proposed layer 1: ChiNext growth sleeve

### Proposed profile name

- `cn_chinext_growth_momentum_quality`

### Role

Board-specific growth sleeve for the ChiNext market.

### Shape

- universe: ChiNext board
- cadence: monthly
- style: growth + momentum + quality
- explicit regime gate: benchmark trend + breadth + liquidity + crowding

### Suggested signals

- revenue growth
- profit growth
- ROE / profitability stability
- 12M-1M momentum
- 60/120-day trend
- liquidity and execution cost
- overheat / crowding penalty

### Suggested behavior

- Can be promoted from the existing research snapshot work.
- Should not be forced to share the same gate model as the industry ETF main line.
- Can later be used as a sleeve inside the combo orchestrator.

## Proposed layer 2: STAR growth sleeve

### Proposed profile name

- `cn_star_growth_momentum_quality`

### Role

Board-specific growth sleeve for the STAR market / STAR50-like universe.

### Shape

- universe: STAR50, or a broader STAR composite universe such as STAR100 /
  STAR200 / special innovation board universes if later evidence supports it
- cadence: monthly
- style: growth + quality + liquidity
- stricter concentration and liquidity controls than ChiNext

### Suggested signals

- revenue / earnings growth
- R&D intensity or innovation proxy
- profitability stability
- 12M-1M momentum
- relative trend vs STAR benchmark
- liquidity / turnover / spread penalty

### Suggested behavior

- Start as a board-level enhancement sleeve, not a narrow stock picker.
- Use a stricter gate than ChiNext because STAR is more concentration- and
  liquidity-sensitive.
- Keep the first version simple and reviewable.

## Proposed layer 3: CN combo orchestrator

### Current problem

`cn_equity_combo` currently reads like a blended research strategy. That is too
ambiguous.

### New role

Make it a true orchestrator / allocator:

- allocates across sleeves
- manages regime budgets
- decides when to emphasize offense vs defense
- does **not** claim to be a single alpha source

### Suggested sleeves

- core industry ETF sleeve
- ChiNext growth sleeve
- STAR growth sleeve
- defensive dividend / quality sleeve

### Suggested runtime shape

```json
{
  "profile": "cn_equity_combo",
  "sleeves": [
    {"profile": "cn_industry_etf_rotation", "weight": 0.40},
    {"profile": "cn_chinext_growth_momentum_quality", "weight": 0.25},
    {"profile": "cn_star_growth_momentum_quality", "weight": 0.15},
    {"profile": "cn_dividend_quality_snapshot", "weight": 0.20}
  ]
}
```

The actual weights should stay configurable, but the separation of responsibilities
should not change.

## Gate model

### Keep / tune

- keep the industry ETF main line as the core A-share runtime strategy
- keep the aggressive ETF variant as the controlled enhancement lane

### Redesign

- ChiNext tactical and ChiNext growth snapshot should be redesigned into the
  ChiNext growth sleeve
- STAR should get its own sleeve instead of being folded into the ChiNext logic
- combo should be rebuilt as an orchestrator

### Do not do

- do not collapse board growth into the industry ETF main line
- do not keep many small variants alive just because they all have slightly
  different filters
- do not promote before the board-specific sleeve beats the current live main
  line on the same horizon

## Evidence sequence

1. Build the board-specific growth sleeve contract.
2. Run same-cycle comparisons against the current industry ETF main line.
3. Add liquidity / spread / crowding penalties.
4. Confirm the sleeve still wins after penalties.
5. Only then decide whether it becomes `live_candidate` or remains research.

## External reference shape

This structure matches the way official board/index sources describe the
universes:

- ChiNext is a growth-oriented Shenzhen board universe with strong innovation
  characteristics.
- STAR Market / STAR50 is the Shanghai innovation board universe, with a
  naturally higher concentration and liquidity sensitivity.

That is why both should be modeled as dedicated sleeves instead of generic
tactical leftovers.

## Reference anchors

- SSE official STAR 50 / STAR 100 / STAR 200 index construction rules
- SSE official index and fund disclosures for STAR-linked products
- MSCI factor index families for growth / quality / momentum / low volatility
- EDHEC and AQR trend-following research for regime gating patterns
