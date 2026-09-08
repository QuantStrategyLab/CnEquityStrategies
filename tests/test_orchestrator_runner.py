"""Tests for CnProxyBacktestRunner + BacktestOrchestrator integration."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from cn_equity_strategies.backtest.orchestrator_runner import (
    CnProxyBacktestRunner,
    SUPPORTED_PROFILES,
    _metrics_to_backtest_result,
)
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_MIN_HISTORY_DAYS,
    PROFILE_NAME,
)


class CnProxyBacktestRunnerTests(unittest.TestCase):
    def test_calmar_keeps_cagr_sign_and_zero_drawdown_is_undefined(self) -> None:
        cases = ((-0.1, -0.2, -0.5), (0.1, -0.2, 0.5), (0.0, -0.2, 0.0), (0.1, 0.0, None))
        for cagr, max_drawdown, expected in cases:
            with self.subTest(cagr=cagr, max_drawdown=max_drawdown):
                result = _metrics_to_backtest_result(
                    strategy_profile=PROFILE_NAME,
                    params={},
                    metrics={"annual_return": cagr, "max_drawdown": max_drawdown},
                    start_date=date(2024, 1, 1),
                    end_date=date(2024, 12, 31),
                    run_duration_seconds=0.0,
                )
                self.assertEqual(result.calmar_ratio, expected)
                self.assertIsNone(result.validation_identity)

    def test_supported_profile_includes_index_etf(self) -> None:
        self.assertIn(PROFILE_NAME, SUPPORTED_PROFILES)

    def test_supported_profile_includes_chinext_tactical(self) -> None:
        self.assertIn("cn_chinext_tactical_rotation", SUPPORTED_PROFILES)

    def test_run_returns_backtest_result(self) -> None:
        runner = CnProxyBacktestRunner(synthetic_days=400)
        result = runner.run(
            PROFILE_NAME,
            {"min_history_days": DEFAULT_MIN_HISTORY_DAYS},
            start_date=date(2023, 6, 1),
            end_date=date(2024, 6, 1),
        )
        self.assertEqual(result.strategy_profile, PROFILE_NAME)
        self.assertEqual(result.domain, "cn_equity")
        self.assertIsNotNone(result.sharpe_ratio)
        self.assertGreater(result.observation_count, 0)
        self.assertFalse(runner.last_daily_returns.empty)
        self.assertGreaterEqual(runner.last_daily_returns.index.min().date(), date(2023, 6, 1))
        self.assertLessEqual(runner.last_daily_returns.index.max().date(), date(2024, 6, 1))
        self.assertEqual(result.observation_count, len(runner.last_daily_returns))

    def test_unsupported_profile_raises(self) -> None:
        runner = CnProxyBacktestRunner(synthetic_days=100)
        with self.assertRaises(ValueError):
            runner.run("unknown_profile", {})

    def test_candidate_parameter_changes_actual_signal_and_returns(self) -> None:
        runner = CnProxyBacktestRunner(synthetic_days=700)
        active = runner.run(PROFILE_NAME, {"min_history_days": 220, "min_momentum": 0.0})
        cash = runner.run(PROFILE_NAME, {"min_history_days": 220, "min_momentum": 999.0})
        self.assertGreater(active.total_return, 0.0)
        self.assertEqual(cash.total_return, 0.0)
        self.assertEqual(cash.params["min_momentum"], 999.0)

    def test_unknown_candidate_parameter_is_not_silently_ignored(self) -> None:
        runner = CnProxyBacktestRunner(synthetic_days=700)
        with self.assertRaises(TypeError):
            runner.run(PROFILE_NAME, {"min_history_days": 220, "typo_momentum": 10})


class WalkForwardPilotTests(unittest.TestCase):
    def test_walk_forward_produces_one_result_per_window(self) -> None:
        from quant_platform_kit.strategy_lifecycle.backtest_orchestrator import BacktestOrchestrator
        from quant_platform_kit.strategy_lifecycle.performance_store import PerformanceStore

        with tempfile.TemporaryDirectory() as tmp:
            store = PerformanceStore(local_root=Path(tmp))
            orchestrator = BacktestOrchestrator(store=store)
            orchestrator.register_runner("cn_equity", CnProxyBacktestRunner(synthetic_days=700))
            windows = (
                (date(2023, 6, 1), date(2023, 12, 31)),
                (date(2024, 1, 1), date(2024, 6, 30)),
            )
            results = orchestrator.walk_forward(
                PROFILE_NAME,
                domain="cn_equity",
                params={"min_history_days": DEFAULT_MIN_HISTORY_DAYS},
                windows=windows,
            )
            self.assertEqual(len(results), 2)
            self.assertTrue(all(item.strategy_profile == PROFILE_NAME for item in results))


if __name__ == "__main__":
    unittest.main()
