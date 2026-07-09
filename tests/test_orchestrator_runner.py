"""Tests for CnProxyBacktestRunner + BacktestOrchestrator integration."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from cn_equity_strategies.backtest.orchestrator_runner import CnProxyBacktestRunner, SUPPORTED_PROFILES
from cn_equity_strategies.strategies.cn_index_etf_tactical_rotation import (
    DEFAULT_MIN_HISTORY_DAYS,
    PROFILE_NAME,
)


class CnProxyBacktestRunnerTests(unittest.TestCase):
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

    def test_unsupported_profile_raises(self) -> None:
        runner = CnProxyBacktestRunner(synthetic_days=100)
        with self.assertRaises(ValueError):
            runner.run("unknown_profile", {})


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
