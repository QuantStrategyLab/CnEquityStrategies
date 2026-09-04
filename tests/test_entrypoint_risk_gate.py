from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from quant_platform_kit.common.models import PortfolioSnapshot, Position
from quant_platform_kit.common.strategy_contracts import BudgetIntent, PositionTarget, StrategyContext, StrategyDecision

from cn_equity_strategies.entrypoints._common import apply_risk_gate


def _portfolio_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime(2026, 8, 5, tzinfo=timezone.utc),
        total_equity=100_000.0,
    )


def test_apply_risk_gate_enriches_stop_loss_diagnostics_from_portfolio() -> None:
    snapshot = PortfolioSnapshot(
        as_of=datetime(2026, 7, 9, tzinfo=timezone.utc),
        total_equity=1000.0,
        positions=(
            Position(
                symbol="510300",
                quantity=100.0,
                market_value=700.0,
                average_cost=10.0,
            ),
        ),
        metadata={"consecutive_losses": 2},
    )
    ctx = StrategyContext(
        as_of=snapshot.as_of,
        portfolio=snapshot,
        market_data={},
        state={},
        runtime_config={},
    )
    decision = StrategyDecision(
        positions=(PositionTarget(symbol="510300", target_weight=0.5),),
    )
    result = apply_risk_gate(decision, ctx=ctx)

    assert result.positions == ()
    assert "rejected:stop_loss" in result.risk_flags
    assert result.diagnostics.get("unrealized_pnl_pct") == -0.3


def test_apply_risk_gate_rejects_circuit_breaker_from_portfolio() -> None:
    snapshot = PortfolioSnapshot(
        as_of=datetime(2026, 7, 9, tzinfo=timezone.utc),
        total_equity=1000.0,
        metadata={"consecutive_losses": 6},
    )
    ctx = StrategyContext(
        as_of=snapshot.as_of,
        portfolio=snapshot,
        market_data={},
        state={},
        runtime_config={},
    )
    decision = StrategyDecision(
        positions=(PositionTarget(symbol="510300", target_weight=0.2),),
    )
    result = apply_risk_gate(decision, ctx=ctx)

    assert result.positions == ()
    assert "rejected:circuit_breaker" in result.risk_flags


def test_apply_risk_gate_allows_explicit_unlevered_ten_percent_default() -> None:
    decision = StrategyDecision(
        positions=(PositionTarget(symbol="510300", target_weight=0.10),),
    )

    result = apply_risk_gate(
        decision,
        portfolio_snapshot=_portfolio_snapshot(),
        product_leverage_factors={"510300": 1},
    )

    assert result.positions == decision.positions
    assert result.risk_flags == ("risk_gate:passed",)


def test_apply_risk_gate_default_contract_rejects_unauthorized_positions() -> None:
    cases = (
        (
            (PositionTarget(symbol="510300", target_weight=0.11),),
            {"510300": 1},
            "rejected:concentration",
        ),
        (
            (
                PositionTarget(symbol="510300", target_weight=0.05),
                PositionTarget(symbol="510500", target_weight=0.05),
            ),
            {"510300": 1, "510500": 1},
            "rejected:too_many_positions",
        ),
        ((PositionTarget(symbol="510300", target_weight=0.10),), None, "rejected:leverage_classification"),
        ((PositionTarget(symbol="510300", target_weight=0.10),), {"510300": 2}, "rejected:leverage_classification"),
        ((PositionTarget(symbol="510300", target_weight=0.10),), {"510500": 1}, "rejected:leverage_classification"),
    )

    for positions, factors, expected_flag in cases:
        decision = StrategyDecision(
            positions=positions,
            budgets=(BudgetIntent(name="risk_budget", amount=1.0),),
        )
        result = apply_risk_gate(
            decision,
            max_single_weight=1.0,
            portfolio_snapshot=_portfolio_snapshot(),
            product_leverage_factors=factors,
        )

        assert result.positions == ()
        assert result.budgets == ()
        assert result.risk_flags == (expected_flag,)


def test_apply_risk_gate_rejects_missing_or_invalid_snapshot() -> None:
    decision = StrategyDecision(
        positions=(PositionTarget(symbol="510300", target_weight=0.10),),
        budgets=(BudgetIntent(name="risk_budget", amount=1.0),),
    )

    for snapshot, reason in ((None, "missing_portfolio_snapshot"), ({"total_equity": float("nan")}, "invalid_portfolio_snapshot")):
        result = apply_risk_gate(
            decision,
            portfolio_snapshot=snapshot,
            product_leverage_factors={"510300": 1},
        )

        assert result.positions == ()
        assert result.budgets == ()
        assert result.risk_flags == ("rejected:risk_engine",)
        assert result.diagnostics["reason"] == reason


def test_apply_risk_gate_rejects_non_approve_engine_action() -> None:
    decision = StrategyDecision(
        positions=(PositionTarget(symbol="510300", target_weight=0.10),),
        budgets=(BudgetIntent(name="risk_budget", amount=1.0),),
    )
    engine = Mock()
    engine.assess.return_value = SimpleNamespace(action="watch", reason="not approved")

    with patch("quant_platform_kit.risk.gate.build_risk_engine", return_value=engine):
        result = apply_risk_gate(
            decision,
            portfolio_snapshot=_portfolio_snapshot(),
            product_leverage_factors={"510300": 1},
        )

    assert result.positions == ()
    assert result.budgets == ()
    assert result.risk_flags == ("rejected:risk_engine",)
    assert result.diagnostics["reason"] == "not approved"
