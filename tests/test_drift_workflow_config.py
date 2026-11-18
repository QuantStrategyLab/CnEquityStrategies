from pathlib import Path

import yaml


def _load_workflow(name: str) -> tuple[str, dict]:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / name
    text = path.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_drift_workflow_wires_real_snapshot_history_and_preflight_bundle() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "drift-check.yml").read_text(encoding="utf-8")

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
    drift_text, drift_data = _load_workflow("drift-check.yml")
    reusable_text, reusable_data = _load_workflow("reusable-drift-check.yml")

    drift_on = drift_data.get("on", drift_data.get(True))
    dispatch_input = drift_on["workflow_dispatch"]["inputs"]["disable_legacy_pat_fallback"]
    assert dispatch_input["type"] == "boolean"
    assert dispatch_input["required"] is False
    assert dispatch_input["default"] is False

    preflight_steps = {
        step["name"]: step for step in drift_data["jobs"]["preflight_backtests"]["steps"]
    }
    creds_env = preflight_steps["Check optional GitHub App credentials"]["env"]
    assert creds_env["DRIFT_APP_ID"] == "${{ secrets.QSL_DRIFT_APP_ID }}"
    assert creds_env["DRIFT_APP_KEY"] == "${{ secrets.QSL_DRIFT_APP_PRIVATE_KEY }}"
    assert creds_env["LEGACY_APP_ID"] == "${{ secrets.QSL_GITHUB_APP_ID }}"
    assert creds_env["LEGACY_APP_KEY"] == "${{ secrets.QSL_GITHUB_APP_PRIVATE_KEY }}"

    mint_step = preflight_steps["Mint optional GitHub App token"]
    assert mint_step["uses"].startswith(
        "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349"
    )
    assert mint_step["continue-on-error"] == (
        "${{ !(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback) }}"
    )
    assert mint_step["with"]["repositories"] == "CnEquitySnapshotPipelines"
    assert mint_step["with"]["permission-contents"] == "read"
    assert mint_step["with"]["permission-actions"] == "read"

    download_step = preflight_steps["Download latest trusted market history"]
    assert 'if [ "${DISABLE_LEGACY_PAT_FALLBACK:-false}" = "true" ] && [ -z "${APP_TOKEN:-}" ]; then' in download_step["run"]
    assert "steps.app_token.outputs.token" in download_step["env"]["GH_TOKEN"]
    assert "!(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback)" in download_step["env"]["GH_TOKEN"]

    drift_job = drift_data["jobs"]["drift"]
    assert drift_job["with"]["disable_legacy_pat_fallback"] == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback }}"
    )
    assert drift_job["secrets"]["qsl_drift_app_id"] == (
        "${{ secrets.QSL_DRIFT_APP_ID || secrets.QSL_GITHUB_APP_ID }}"
    )
    assert drift_job["secrets"]["qsl_drift_app_private_key"] == (
        "${{ secrets.QSL_DRIFT_APP_PRIVATE_KEY || secrets.QSL_GITHUB_APP_PRIVATE_KEY }}"
    )
    assert drift_job["secrets"]["snapshot_repository_token"] == (
        "${{ !(github.event_name == 'workflow_dispatch' && inputs.disable_legacy_pat_fallback) && (secrets.SNAPSHOT_REPOSITORY_TOKEN || secrets.QSL_REPO_SYNC_TOKEN || github.token) || '' }}"
    )

    reusable_on = reusable_data.get("on", reusable_data.get(True))
    reusable_input = reusable_on["workflow_call"]["inputs"]["disable_legacy_pat_fallback"]
    assert reusable_input["type"] == "boolean"
    assert reusable_input["required"] is False
    assert reusable_input["default"] is False
    assert "qsl_drift_app_id" in reusable_on["workflow_call"]["secrets"]
    assert "qsl_drift_app_private_key" in reusable_on["workflow_call"]["secrets"]

    reusable_steps = {
        step["name"]: step for step in reusable_data["jobs"]["drift"]["steps"]
    }
    assert 'snapshot_repo_name=${snapshot_repo#*/}' in reusable_steps["Validate trusted caller"]["run"]

    reusable_mint = reusable_steps["Mint snapshot GitHub App token"]
    assert reusable_mint["uses"].startswith(
        "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349"
    )
    assert reusable_mint["continue-on-error"] == "${{ !inputs.disable_legacy_pat_fallback }}"
    assert reusable_mint["with"]["owner"] == "QuantStrategyLab"
    assert reusable_mint["with"]["repositories"] == "${{ steps.trusted_caller.outputs.snapshot_repo_name }}"
    assert reusable_mint["with"]["permission-contents"] == "read"
    assert reusable_mint["with"]["permission-actions"] == "read"

    assert_step = reusable_steps["Assert snapshot GitHub App token when legacy fallback is disabled"]
    assert assert_step["if"] == "inputs.disable_legacy_pat_fallback"
    assert 'if [ -z "${APP_TOKEN:-}" ]; then' in assert_step["run"]

    checkout_snapshot = reusable_steps["Checkout snapshot pipeline repo"]
    assert checkout_snapshot["with"]["token"] == (
        "${{ (inputs.disable_legacy_pat_fallback && steps.snapshot_app_token.outputs.token) || (!inputs.disable_legacy_pat_fallback && (steps.snapshot_app_token.outputs.token || secrets.snapshot_repository_token || github.token)) || '' }}"
    )
    assert "qsl_drift_app_id" in drift_text
    assert "disable_legacy_pat_fallback" in reusable_text
