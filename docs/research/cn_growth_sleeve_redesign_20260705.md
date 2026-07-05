# CN Growth Sleeve Redesign Plan (2026-07-05)

> This is an engineering/research plan, not investment advice.

## Why this needs a redesign

The earlier read treated ChiNext and STAR as weaker or secondary because the
existing strategy shapes were too narrow. That was the wrong conclusion.

Recent market evidence shows both growth boards can be strong regime leaders:

- ChiNext has printed major highs and has materially outperformed in the current
  growth-led phase.
- STAR market / STAR50 has also led in 2026 on a number of public data sources.

So the issue is not "these boards are weak." The issue is:

1. the current strategy shapes are too small or too tactical,
2. the board-specific regime is not modeled explicitly enough,
3. the combo layer is using the wrong abstraction.

## Design conclusion

ChiNext and STAR should be treated as **independent growth sleeves**, not as
subordinate research leftovers.

That means:

- the board itself is a first-class universe,
- the sleeve gets its own regime gate,
- the sleeve gets its own growth / quality / liquidity logic,
- the sleeve can later become a combo component, but not as a dumb appendage.

## Recommended target architecture

### 1) ChiNext growth sleeve

Proposed new shape:

- universe: ChiNext board
- style: growth + momentum + quality
- cadence: monthly
- gating: benchmark trend filter + liquidity + overheat / crowding penalty

Key signals:

- revenue growth
- profit growth
- ROE / profitability stability
- 12M-1M momentum
- 60/120-day trend
- liquidity and execution cost
- board breadth / regime filter

This should evolve from `cn_chinext_tactical_rotation` into a more explicit
`cn_chinext_growth_momentum_quality` line.

### 2) STAR growth sleeve

Proposed new shape:

- universe: STAR50 or STAR composite / broader STAR universe
- style: growth + quality + liquidity with heavier risk controls
- cadence: monthly
- gating: stricter liquidity and concentration constraints than ChiNext

STAR should not start as a narrow champion-picking experiment. It should begin
as a board-level enhancement sleeve so the design matches how the market is
actually behaving.

### 3) CN combo as allocator, not alpha claimant

`cn_equity_combo` should be rebuilt as a composition/orchestration layer:

- industry ETF core
- ChiNext growth sleeve
- STAR growth sleeve
- defensive dividend/quality sleeve

The combo should decide weights and risk budgets. It should not pretend to be a
single alpha source.

## What should change in policy language

- `research_backtest_only` should no longer imply "low priority" for ChiNext or
  STAR.
- `live_candidate` should only be assigned after the board-specific sleeve beats
  the current main line on the same horizon.
- `cn_chinext_tactical_rotation` and `cn_chinext_growth_momentum_quality_snapshot`
  should be treated as **growth-sleeve candidates**, not discardable leftovers.

## What not to do

- Do not promote a board sleeve just because a short window is hot.
- Do not merge board growth sleeves into the industry ETF main line.
- Do not keep multiple weak variants alive just because each one has a slightly
  different filter.
- Do not force live enablement before the board-specific gate is complete.

## Proposed implementation sequence

1. Define a board-specific growth sleeve contract for ChiNext.
2. Define a board-specific growth sleeve contract for STAR.
3. Reframe `cn_equity_combo` as a true allocator/orchestrator.
4. Re-run the same-cycle comparisons against the current industry ETF main line.
5. Promote only if the sleeve is still competitive after liquidity and risk
   penalties.

## Practical status recommendation

- `cn_industry_etf_rotation`: keep as the core A-share main line.
- `cn_chinext_*`: redesign into a first-class growth sleeve.
- `cn_star_*`: add as a separate growth sleeve once the STAR contract is
  defined.
- `cn_equity_combo`: rebuild later as composition logic.

## Reference anchors

These are the main external reference families used for the redesign:

- STAR 50 / STAR 100 / STAR 200 official index construction rules from SSE.
- ChiNext as a board-level growth universe with its own index structure.
- MSCI factor index families for growth, quality, momentum, value, and low-volatility framing.
- EDHEC / AQR trend-following research for regime and gating logic.
