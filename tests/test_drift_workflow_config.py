from pathlib import Path


def _read_workflow(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_drift_workflow_wires_real_snapshot_history_and_preflight_bundle() -> None:
    workflow = _read_workflow("drift-check.yml")

    assert "preflight_backtests:" in workflow
    assert "needs: preflight_backtests" in workflow
    assert "snapshot_repository_ref: ${{ steps.snapshot-input.outputs.snapshot_repository_ref }}" in workflow
    assert "id: snapshot-input" in workflow
    assert 'print(run["head_sha"])' in workflow
    assert "snapshot_repository_ref: ${{ needs.preflight_backtests.outputs.snapshot_repository_ref }}" in workflow
    assert "Download latest trusted market history" in workflow
    assert "gh api --paginate --slurp" in workflow
    assert "trusted-snapshot-runs.json" in workflow
    assert "cn-equity-market-history-" in workflow
    assert '"path": ".github/workflows/publish-market-history.yml"' in workflow
    assert '"conclusion": "success"' in workflow
    assert "cn_etf_market_history.csv" in workflow
    assert "repository: QuantStrategyLab/QuantPlatformKit" in workflow
    assert "ref: c7646a7168b3dafa763ef7751a182d23e8de7790" in workflow
    assert "quant_platform_kit_ref: c7646a7168b3dafa763ef7751a182d23e8de7790" in workflow
    assert "python -m pip install --no-deps -e external/QuantPlatformKit" in workflow
    assert "scripts/run_walk_forward_backtest.py" in workflow
    assert '"--list-profiles"' in workflow
    assert '"--store-root"' in workflow
    assert '"--market-history"' in workflow
    assert '"--returns-output"' in workflow
    assert "LIFECYCLE_PREFLIGHT_BUNDLE_ROOT" in workflow
    assert "Upload lifecycle preflight artifact" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert workflow.count("github.ref == format('refs/heads/{0}', github.event.repository.default_branch)") == 2
    assert "uses: ./.github/workflows/reusable-drift-check.yml" in workflow
    assert "strategy_domain: cn_equity" in workflow
    assert "caller_event_name: ${{ github.event_name }}" in workflow
    assert "caller_pr_head_repository: ${{ github.event.pull_request.head.repo.full_name || '' }}" in workflow
    assert "snapshot_repository: QuantStrategyLab/CnEquitySnapshotPipelines" in workflow
    assert "snapshot_checkout_path: external/CnEquitySnapshotPipelines" in workflow
    assert "ai_service_url: ${{ vars.AI_SERVICE_URL }}" in workflow
    assert "lifecycle_preflight_artifact: lifecycle-preflight-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
    assert "codex_audit_service_url:" not in workflow
    assert "secrets.SNAPSHOT_REPOSITORY_TOKEN || secrets.QSL_REPO_SYNC_TOKEN || github.token" in workflow


def test_drift_workflow_supports_readonly_app_and_no_fallback_mode() -> None:
    drift_workflow = _read_workflow("drift-check.yml")
    reusable_workflow = _read_workflow("reusable-drift-check.yml")

    assert "workflow_dispatch:\n    inputs:\n      disable_legacy_pat_fallback:" in drift_workflow
    assert "DRIFT_APP_ID: ${{ secrets.QSL_DRIFT_APP_ID }}" in drift_workflow
    assert "DRIFT_APP_KEY: ${{ secrets.QSL_DRIFT_APP_PRIVATE_KEY }}" in drift_workflow
    assert "LEGACY_APP_ID: ${{ secrets.QSL_GITHUB_APP_ID }}" in drift_workflow
    assert "LEGACY_APP_KEY: ${{ secrets.QSL_GITHUB_APP_PRIVATE_KEY }}" in drift_workflow
    assert "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2" in drift_workflow
    assert "continue-on-error: ${{ !(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback) }}" in drift_workflow
    assert "repositories: CnEquitySnapshotPipelines" in drift_workflow
    assert "permission-contents: read" in drift_workflow
    assert "permission-actions: read" in drift_workflow
    assert 'if [ "${DISABLE_LEGACY_PAT_FALLBACK:-false}" = "true" ] && [ -z "${APP_TOKEN:-}" ]; then' in drift_workflow
    assert (
        "GH_TOKEN: ${{ (github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback && steps.app_token.outputs.token) "
        "|| (!(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback) "
        "&& (steps.app_token.outputs.token || secrets.SNAPSHOT_REPOSITORY_TOKEN || secrets.QSL_REPO_SYNC_TOKEN || github.token)) || '' }}"
    ) in drift_workflow
    assert "disable_legacy_pat_fallback: ${{ github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback }}" in drift_workflow
    assert "qsl_drift_app_id: ${{ secrets.QSL_DRIFT_APP_ID || secrets.QSL_GITHUB_APP_ID }}" in drift_workflow
    assert "qsl_drift_app_private_key: ${{ secrets.QSL_DRIFT_APP_PRIVATE_KEY || secrets.QSL_GITHUB_APP_PRIVATE_KEY }}" in drift_workflow
    assert (
        "snapshot_repository_token: ${{ !(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback) "
        "&& (secrets.SNAPSHOT_REPOSITORY_TOKEN || secrets.QSL_REPO_SYNC_TOKEN || github.token) || '' }}"
    ) in drift_workflow

    assert "disable_legacy_pat_fallback:" in reusable_workflow
    assert "qsl_drift_app_id:" in reusable_workflow
    assert "qsl_drift_app_private_key:" in reusable_workflow
    assert 'echo "snapshot_repo_name=${snapshot_repo#*/}" >> "$GITHUB_OUTPUT"' in reusable_workflow
    assert "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349 # v2" in reusable_workflow
    assert "continue-on-error: ${{ !inputs.disable_legacy_pat_fallback }}" in reusable_workflow
    assert "owner: QuantStrategyLab" in reusable_workflow
    assert "repositories: ${{ steps.trusted_caller.outputs.snapshot_repo_name }}" in reusable_workflow
    assert "permission-contents: read" in reusable_workflow
    assert "permission-actions: read" in reusable_workflow
    assert "if: inputs.disable_legacy_pat_fallback" in reusable_workflow
    assert 'if [ -z "${APP_TOKEN:-}" ]; then' in reusable_workflow
    assert (
        "token: ${{ (inputs.disable_legacy_pat_fallback && steps.snapshot_app_token.outputs.token) "
        "|| (!inputs.disable_legacy_pat_fallback && (steps.snapshot_app_token.outputs.token || secrets.snapshot_repository_token || github.token)) || '' }}"
    ) in reusable_workflow
