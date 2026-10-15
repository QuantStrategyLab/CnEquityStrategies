"""Offline job admission; synthetic fixtures are not market evidence."""


from __future__ import annotations


from datetime import datetime, timezone


import json


import os


from pathlib import Path


from unittest.mock import Mock, patch


from types import SimpleNamespace


import hashlib


import importlib


import io


import urllib.error


import subprocess


import sys


import pytest


from cn_equity_strategies.backtest import index_etf_research_task as job


from quant_platform_kit.strategy_lifecycle.research_task import build_strategy_diagnosis_task


NOW = datetime(2026, 9, 9, 8, tzinfo=timezone.utc)


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz)


REVISION = "c" * 40


ENV = {
    "GITHUB_REPOSITORY": "QuantStrategyLab/CnEquityStrategies",
    "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_WORKFLOW_REF": "QuantStrategyLab/CnEquityStrategies/.github/workflows/cn-index-etf-research.yml@refs/heads/main",
    "GITHUB_RUN_ID": "12345", "GITHUB_SHA": "a" * 40,
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://synthetic.invalid/oidc",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic-test-only",
    "AI_SERVICE_URL": "https://synthetic.invalid",
}


def write(path, value):
    path.write_text(json.dumps(value))
    return path


@pytest.fixture(autouse=True)
def isolated():
    with patch.dict(os.environ, ENV, clear=True), patch.object(job, "_now", return_value=NOW):
        yield


def task(revision=REVISION):
    return build_strategy_diagnosis_task(
        event_key="a" * 12, created_at="2026-09-09T06:17:00Z", candidate_id=job.PROFILE,
        candidate_kind="individual", domain="cn_equity", strategy_repository=job.STRATEGY_REPOSITORY,
        evidence={"p1_input_digest": "1" * 64, "p2_config_digest": "2" * 64,
                  "p3_evidence_id": "3" * 64, "strategy_revision": revision, "producer_revision": "d" * 40},
    )


def watcher(revision=REVISION):
    return {"research_task_source_snapshot": {"schema_version": "qsl_research_task_source_snapshot.v1",
            "data_status": "ready", "tasks": [task(revision)]}}


def test_missing_or_disabled_policy_never_imports_runner_or_calls_model(tmp_path):
    with patch.object(job, "_load_runtime") as runtime:
        result = job.run_from_watcher(watcher(), policy_path=tmp_path / "absent")
        assert result["reason"] == "cn_research_not_configured"
        with patch.object(job, "_read_policy", return_value={"enabled": False}):
            result = job.run_from_watcher(watcher())
            assert result["reason"] == "cn_research_disabled"
    runtime.assert_not_called()


@pytest.mark.parametrize("change", [{"AI_SERVICE_TOKEN": "synthetic-static"},
    {"ACTIONS_ID_TOKEN_REQUEST_URL": ""}, {"ACTIONS_ID_TOKEN_REQUEST_TOKEN": ""},
    {"GITHUB_REF": "refs/heads/feature"}, {"GITHUB_EVENT_NAME": "pull_request"},
    {"GITHUB_WORKFLOW_REF": "QuantStrategyLab/CnEquityStrategies/.github/workflows/unapproved.yml@refs/heads/main"}])
def test_workflow_and_oidc_are_required_before_runtime(change):
    with patch.object(job, "_read_policy", return_value={"enabled": True}), \
            patch.dict(os.environ, change), patch.object(job, "_load_runtime") as runtime:
        assert job.run_from_watcher(watcher())["reason"] == "cn_research_workflow_auth_required"
    runtime.assert_not_called()


def test_task_is_verified_and_never_supplies_the_observation_clock():
    verified = job._select_task(watcher(), REVISION, NOW)
    assert verified["created_at"] == "2026-09-09T06:17:00Z"
    invalid = watcher()
    invalid["research_task_source_snapshot"]["tasks"][0]["experiment"]["max_runs"] = 2
    with pytest.raises(ValueError):
        job._select_task(invalid, REVISION, NOW)
    with pytest.raises(ValueError):
        job._select_task(watcher(), "e" * 40, NOW)


@pytest.mark.parametrize("change", [{"as_of": None}, {"as_of": "2026-09-10"}, {"as_of": "2026-09-01"},
    {"drift_score": True}, {"drift_score": float("nan")}, {"status": "healthy"},
    {"source_revision": "wrong"}, {"strategy_profile": "another"}, {"domain": "us_equity"},
    {"alert_suppressed": True}, {"baseline_available": False}])
def test_real_drift_requires_matching_fresh_actionable_source(tmp_path, change):
    raw = {"strategy_profile": job.PROFILE, "domain": "cn_equity", "source_revision": REVISION,
           "as_of": "2026-09-09", "drift_score": .8, "status": "critical", **change}
    source = write(tmp_path / "drift.json", raw)
    with pytest.raises(ValueError):
        job._read_drift({"path": str(source), "source_revision": REVISION}, NOW)


def test_daily_admission_counts_existing_ticket_utc_created_at(tmp_path):
    assert job.admit_one_new_experiment(tmp_path, NOW.isoformat()) is True
    ticket = {"strategy_profile": job.PROFILE, "domain": "cn_equity", "live_authority_granted": False}
    old_id, new_id = "rpt_" + "a" * 64, "rpt_" + "b" * 64
    write(tmp_path / f"{old_id}.json", {**ticket, "ticket_id": old_id, "created_at": "2026-09-08T23:59:59Z"})
    assert job.admit_one_new_experiment(tmp_path, NOW.isoformat()) is True
    write(tmp_path / f"{new_id}.json", {**ticket, "ticket_id": new_id, "created_at": "2026-09-09T00:00:00Z"})
    assert job.admit_one_new_experiment(tmp_path, NOW.isoformat()) is False


@pytest.mark.parametrize("bad", [{}, {"created_at": "2026-09-09T00:00:00"},
    {"created_at": "2026-09-10T00:00:00Z"}, {"created_at": None}])
def test_daily_admission_unknown_count_fails_closed(tmp_path, bad):
    write(tmp_path / "rpt_bad.json", bad)
    assert job.admit_one_new_experiment(tmp_path, NOW.isoformat()) is False


def test_daily_admission_does_not_add_a_ledger_or_follow_symlinks(tmp_path):
    outside = write(tmp_path / "private", {"created_at": NOW.isoformat()})
    (tmp_path / "rpt_link.json").symlink_to(outside)
    assert job.admit_one_new_experiment(tmp_path, NOW.isoformat()) is False
    assert sorted(path.name for path in tmp_path.iterdir()) == ["private", "rpt_link.json"]


def test_policy_rejects_untrusted_owner_mode_and_symlink(tmp_path):
    path = write(tmp_path / "policy.json", {"enabled": True})
    path.chmod(0o666)
    with pytest.raises(ValueError):
        job._read_policy(path)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        job._read_policy(link)


@pytest.mark.parametrize("source", [None, {}, {"dir_info": {"editable": True}},
    {"vcs_info": {"commit_id": "e" * 40}},
    {"vcs_info": {"vcs": "git", "commit_id": REVISION}, "dir_info": {"editable": True}},
    {"vcs_info": {"vcs": "svn", "commit_id": REVISION}}])
def test_installed_runtime_requires_noneditable_git_commit(source):
    raw = None if source is None else json.dumps(source)
    with patch.object(job.importlib.metadata, "distribution") as distribution:
        distribution.return_value.read_text.return_value = raw
        with pytest.raises(ValueError, match="installed_revision"):
            job._installed_revision("synthetic-package", REVISION)


def test_installed_runtime_accepts_exact_git_commit():
    with patch.object(job.importlib.metadata, "distribution") as distribution:
        distribution.return_value.read_text.return_value = json.dumps({"vcs_info": {"vcs": "git", "commit_id": REVISION}})
        job._installed_revision("synthetic-package", REVISION)


def test_cli_failure_prints_only_sanitized_summary(tmp_path, capsys):
    path = tmp_path / "sensitive-missing.json"
    assert job.main(["--watcher-result", str(path)]) == 3
    output = capsys.readouterr().out
    assert str(path) not in output and "sensitive" not in output
    assert json.loads(output)["live_authority_granted"] is False


@pytest.fixture
def shadow_inputs(tmp_path):
    importlib.import_module("quant_platform_kit")
    from quant_platform_kit.strategy_lifecycle.forward_observation import ForwardObservationPolicy
    from quant_platform_kit.strategy_lifecycle.forward_observation_receipt import build_forward_observation_receipt
    policy_args = dict(candidate_id="cn-frozen-example", strategy_profile=job.PROFILE, domain="cn_equity",
        benchmark_symbol="510300", required_trading_sessions=2, review_milestones=[1],
        automatic_non_live_modes=["shadow"], auto_resume_clean_sessions=1, observation_calendar="XSHG",
        observation_window_type="fixed", observation_start_session="2026-09-07",
        window_rationale_ref="synthetic-test-policy", non_live_evidence_modes=["shadow_decision"])
    policy = ForwardObservationPolicy(**policy_args)
    calendar = write(tmp_path / "sessions.json", ["2026-09-07", "2026-09-08"])
    dependencies = {key: "a" * 64 for key in ("p1_manifest", "p2_config", "p3_evidence", "risk_policy", "strategy_release", "plugin_bundle")}
    observations = []
    previous = None
    for index, day in enumerate(["2026-09-07", "2026-09-08"], 1):
        receipt = build_forward_observation_receipt(policy=policy, observation_session=day, observation_index=index,
            dependency_digests=dependencies, evidence_modes=["shadow_decision"], previous_receipt=previous)
        leg = {key: {"synthetic": True, "value": 0} for key in ("signal", "hypothetical_order", "position", "cost", "return")}
        observations.append(dict(forward_observation_receipt=receipt, baseline_id="cn-baseline",
            observed_at=day + "T16:00:00+08:00", input_snapshot_sha256="a" * 64, candidate=leg, baseline=leg))
        previous = receipt
    identity = {key: "sha256:" + "f" * 64 for key in job._IDENTITY_FIELDS}
    proposal = SimpleNamespace(strategy_profile=job.PROFILE, domain="cn_equity", current_params={"a": 1},
                               proposed_params={"a": 2}, computed_at="2026-09-06T08:00:00Z")
    payload = dict(strategy_profile=job.PROFILE, domain="cn_equity", source_revision=REVISION,
        research_identity=identity, current_params={"a": 1}, proposed_params={"a": 2}, observations=observations)
    observation_path = write(tmp_path / "observations.json", payload)
    binding = dict(forward_policy=policy_args, observation_path=str(observation_path), calendar_path=str(calendar),
        calendar_sha256=hashlib.sha256(calendar.read_bytes()).hexdigest(), baseline_id="cn-baseline",
        frozen_dependency_digests={key: value for key, value in dependencies.items() if key != "p1_manifest"},
        retry_after_seconds=3600)
    return binding, identity, proposal, payload


def test_shadow_requires_complete_real_calendar_and_receipt_chain(shadow_inputs):
    from quant_platform_kit.strategy_lifecycle.paired_shadow_adapter import collect_paired_shadow_for_promotion
    binding, identity, proposal, _ = shadow_inputs
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result["status"] == "complete"
    record = collect_paired_shadow_for_promotion(result["observation"])
    assert record["passed"] and record["no_order"] and not record["live_authority_granted"]


@pytest.mark.parametrize("missing", [False, True])
def test_incomplete_shadow_is_pending_without_fabricating_success(shadow_inputs, missing):
    binding, identity, proposal, payload = shadow_inputs
    path = Path(binding["observation_path"])
    if missing:
        path.unlink()
    else:
        payload["observations"] = payload["observations"][:1]
        write(path, payload)
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result == {"status": "pending", "passed": False, "no_order": True, "live_authority_granted": False,
                      "retry_at": NOW.timestamp() + 3600}


@pytest.mark.parametrize("change", ["params", "source", "calendar", "chain", "backfill", "future", "missing_session"])
def test_shadow_wrong_binding_or_backfilled_evidence_cannot_complete(shadow_inputs, change):
    binding, identity, proposal, payload = shadow_inputs
    if change == "params":
        payload["proposed_params"] = {"a": 3}
    elif change == "source":
        payload["source_revision"] = "e" * 40
    elif change == "calendar":
        binding["calendar_sha256"] = "b" * 64
    elif change == "chain":
        payload["observations"][1]["forward_observation_receipt"]["previous_receipt_sha256"] = "b" * 64
    elif change == "backfill":
        proposal.computed_at = "2026-09-09T00:00:00Z"
    elif change == "future":
        payload["observations"][1]["observed_at"] = "2026-09-10T00:00:00Z"
    else:
        payload["observations"] = payload["observations"][1:]
    write(Path(binding["observation_path"]), payload)
    if change == "calendar":
        with pytest.raises(ValueError, match="shadow_calendar_mismatch"):
            job._make_shadow_reader(binding, identity, REVISION)
        return
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result["status"] == "failed" and result["passed"] is False
    assert "observation" not in result


def test_resolve_research_owner_requires_exact_source_issue_and_body_marker(monkeypatch):
    source = watcher()
    source["issues"] = [{
        "repo": job.ISSUE_REPOSITORY,
        "watcher_issue_key": "watcher-key-1",
        "url": f"https://github.com/{job.ISSUE_REPOSITORY}/issues/123",
        "task": {"event_key": "aaaaaaaaaaaa"},
    }]
    monkeypatch.setenv("STRATEGY_WATCH_SOURCE_REPO", job.ISSUE_REPOSITORY)
    monkeypatch.setenv("GH_TOKEN", "synthetic")
    with patch.object(job, "_github_issue_get", return_value={
        "state": "open", "number": 123,
        "html_url": f"https://github.com/{job.ISSUE_REPOSITORY}/issues/123",
        "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->\noriginal",
    }):
        assert job._resolve_research_owner(source, source["research_task_source_snapshot"]["tasks"][0]) == {
            "repository": job.ISSUE_REPOSITORY, "issue_number": 123, "watcher_issue_key": "watcher-key-1",
        }
    source["issues"][0]["url"] = "https://github.com/QuantStrategyLab/Other/issues/123"
    assert job._resolve_research_owner(source, source["research_task_source_snapshot"]["tasks"][0]) is None


@pytest.mark.parametrize("issue", [
    {"state": "OPEN", "number": 123, "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->"},
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/CnEquitySnapshotPipelines/pull/123",
     "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->"},
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/Other/issues/123",
     "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->"},
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/CnEquitySnapshotPipelines/issues/123",
     "body": "unrelated"},
])
def test_resolve_research_owner_rejects_unverifiable_github_detail(monkeypatch, issue):
    source = watcher()
    source["issues"] = [{
        "repo": job.ISSUE_REPOSITORY,
        "watcher_issue_key": "watcher-key-1",
        "url": f"https://github.com/{job.ISSUE_REPOSITORY}/issues/123",
        "task": {"event_key": "aaaaaaaaaaaa"},
    }]
    monkeypatch.setenv("STRATEGY_WATCH_SOURCE_REPO", job.ISSUE_REPOSITORY)
    monkeypatch.setenv("GH_TOKEN", "synthetic")
    with patch.object(job, "_github_issue_get", return_value=issue):
        assert job._resolve_research_owner(source, source["research_task_source_snapshot"]["tasks"][0]) is None


def _archive_ticket_fixture(tmp_path, *, archived=True, paused=False, stage_status="completed"):
    root = tmp_path / "state"
    ticket_dir = root / "research_promotion_tickets"
    ticket_dir.mkdir(parents=True)
    ticket_path = ticket_dir / ("rpt_" + "a" * 64 + ".json")
    owner = {"repository": job.ISSUE_REPOSITORY, "issue_number": 123, "watcher_issue_key": "watcher-key-1"}
    progress = {
        "identity": {"owner": owner}, "scope_key": "b" * 64,
        "lifecycle": {"archived": archived, "paused": paused, "archive_reason": "idle_timeout"},
        "stages": {"optimize": {"status": stage_status}},
    }
    ticket = SimpleNamespace(
        ticket_id=ticket_path.stem, live_authority_granted=False, state=SimpleNamespace(value="parked"),
        research_progress=progress,
    )
    saved = []
    class Cycle:
        @staticmethod
        def load_research_promotion_ticket(path):
            return ticket
        @staticmethod
        def save_research_promotion_ticket(value, path):
            saved.append(dict(value.research_progress))
        @staticmethod
        def _saved_scope_records(directory, scope_key):
            return [(ticket_path, ticket)]
        @staticmethod
        def _research_directory_lock(directory):
            from contextlib import contextmanager
            @contextmanager
            def lock():
                yield True
            return lock()
    return root, ticket_path, owner, ticket, saved, Cycle


def test_archived_issue_is_patched_once_and_confirmed_delivery_is_idempotent(tmp_path, monkeypatch):
    root, path, owner, ticket, saved, cycle = _archive_ticket_fixture(tmp_path)
    monkeypatch.setattr(job, "STATE_ROOT", root)
    get_calls, patch_calls = [], []
    monkeypatch.setattr(job, "_github_issue_get", lambda repo, number: get_calls.append((repo, number)) or {
        "state": "OPEN", "number": 123,
        "html_url": f"https://github.com/{job.ISSUE_REPOSITORY}/issues/123",
        "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->",
    })
    monkeypatch.setattr(job, "_github_issue_close", lambda repo, number, body: patch_calls.append((repo, number, body)) or {
        "state": "CLOSED", "body": body,
    })
    runtime = SimpleNamespace(cycle=cycle)
    result = {"reason": "research_scope_archived", "ticket_path": str(path)}
    assert job._archive_research_issue(runtime, result, owner)["status"] == "confirmed"
    assert len(patch_calls) == 1
    assert "research-scope-archived:" in patch_calls[0][2]
    assert job._archive_research_issue(runtime, result, owner)["reason"] == "issue_already_archived"
    assert len(patch_calls) == 1
    assert saved[-1]["issue_archive"]["status"] == "confirmed"


def test_unknown_archive_only_gets_on_follow_up_and_never_repatches(tmp_path, monkeypatch):
    root, path, owner, ticket, saved, cycle = _archive_ticket_fixture(tmp_path)
    monkeypatch.setattr(job, "STATE_ROOT", root)
    get_calls, patch_calls = [], []
    monkeypatch.setattr(job, "_github_issue_get", lambda repo, number: get_calls.append((repo, number)) or {
        "state": "OPEN", "number": 123,
        "html_url": f"https://github.com/{job.ISSUE_REPOSITORY}/issues/123",
        "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->",
    })
    monkeypatch.setattr(job, "_github_issue_close", lambda *_: patch_calls.append(1) or (_ for _ in ()).throw(TimeoutError()))
    runtime = SimpleNamespace(cycle=cycle)
    result = {"reason": "research_scope_archived", "ticket_path": str(path)}
    assert job._archive_research_issue(runtime, result, owner)["reason"] == "issue_archive_unknown"
    assert len(patch_calls) == 1
    assert job._archive_research_issue(runtime, result, owner)["reason"] == "issue_archive_unknown"
    assert len(patch_calls) == 1
    assert len(get_calls) == 2


@pytest.mark.parametrize("kwargs", [
    {"paused": True}, {"stage_status": "unknown"}, {"archived": False},
])
def test_archive_requires_verified_terminal_ticket_without_protection(tmp_path, monkeypatch, kwargs):
    root, path, owner, ticket, saved, cycle = _archive_ticket_fixture(tmp_path, **kwargs)
    monkeypatch.setattr(job, "STATE_ROOT", root)
    get = Mock()
    close = Mock()
    monkeypatch.setattr(job, "_github_issue_get", get)
    monkeypatch.setattr(job, "_github_issue_close", close)
    result = job._archive_research_issue(SimpleNamespace(cycle=cycle), {"ticket_path": str(path)}, owner)
    assert result["reason"] == "research_ticket_not_archiveable"
    get.assert_not_called()
    close.assert_not_called()


def test_archive_is_blocked_by_active_ticket_in_same_scope(tmp_path, monkeypatch):
    root, path, owner, ticket, saved, cycle = _archive_ticket_fixture(tmp_path)
    active = SimpleNamespace(
        ticket_id="rpt_" + "c" * 64, live_authority_granted=False,
        state=SimpleNamespace(value="awaiting_human"),
        research_progress={
            "identity": {"owner": owner}, "scope_key": "b" * 64,
            "lifecycle": {"archived": False, "paused": False},
            "stages": {"optimize": {"status": "completed"}},
        },
    )
    cycle._saved_scope_records = staticmethod(lambda directory, scope_key: [(path, ticket), (path, active)])
    monkeypatch.setattr(job, "STATE_ROOT", root)
    get = Mock()
    close = Mock()
    monkeypatch.setattr(job, "_github_issue_get", get)
    monkeypatch.setattr(job, "_github_issue_close", close)
    result = job._archive_research_issue(SimpleNamespace(cycle=cycle), {"ticket_path": str(path)}, owner)
    assert result["reason"] == "research_ticket_not_archiveable"
    get.assert_not_called()
    close.assert_not_called()


@pytest.mark.parametrize("issue", [
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/CnEquitySnapshotPipelines/issues/123",
     "body": "unrelated"},
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/CnEquitySnapshotPipelines/pull/123",
     "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->"},
    {"state": "OPEN", "number": 123, "html_url": "https://github.com/QuantStrategyLab/Other/issues/123",
     "body": "<!-- strategy-optimization-watcher:watcher-key-1 -->"},
])
def test_archive_rechecks_exact_issue_before_patch(tmp_path, monkeypatch, issue):
    root, path, owner, ticket, saved, cycle = _archive_ticket_fixture(tmp_path)
    monkeypatch.setattr(job, "STATE_ROOT", root)
    monkeypatch.setattr(job, "_github_issue_get", lambda *_: issue)
    close = Mock()
    monkeypatch.setattr(job, "_github_issue_close", close)
    result = job._archive_research_issue(SimpleNamespace(cycle=cycle), {"ticket_path": str(path)}, owner)
    assert result["reason"] == "issue_archive_unknown"
    close.assert_not_called()


def test_shadow_cannot_label_future_sessions_as_completed(shadow_inputs):
    binding, identity, proposal, _ = shadow_inputs
    # The second receipt claims Sep 8, but its timestamp is still Sep 7.
    payload = json.loads(Path(binding["observation_path"]).read_text())
    payload["observations"][1]["observed_at"] = "2026-09-07T17:00:00+08:00"
    write(Path(binding["observation_path"]), payload)
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result["status"] == "failed" and result["passed"] is False


@pytest.mark.parametrize("field", ["forward_policy", "calendar_sha256", "frozen_dependency_digests", "baseline_id"])
def test_bad_shadow_configuration_is_rejected_before_constructing_a_callback(shadow_inputs, field):
    binding, identity, _, _ = shadow_inputs
    binding[field] = {} if field.endswith("digests") or field == "forward_policy" else ""
    with pytest.raises(ValueError):
        job._make_shadow_reader(binding, identity, REVISION)


@pytest.mark.parametrize("binding", [None,
    {"sync_url": "http://synthetic.invalid/sync", "pull_url": "https://synthetic.invalid/pull"},
    {"sync_url": "https://synthetic.invalid/sync", "pull_url": "https://different.invalid/pull"}])
def test_console_missing_or_wrong_origin_constructs_no_network_callback(binding):
    importlib.import_module("quant_platform_kit")
    with patch("urllib.request.urlopen", side_effect=AssertionError("unexpected request")) as http:
        with pytest.raises(ValueError):
            job._console_bindings(binding)
    http.assert_not_called()


def test_shadow_cannot_relabel_old_sessions_with_postproposal_timestamps(shadow_inputs):
    binding, identity, proposal, payload = shadow_inputs
    proposal.computed_at = "2026-09-09T07:40:00Z"
    payload["observations"][0]["observed_at"] = "2026-09-09T07:50:00Z"
    payload["observations"][1]["observed_at"] = "2026-09-09T07:51:00Z"
    write(Path(binding["observation_path"]), payload)
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result["status"] == "failed" and "observation" not in result


@pytest.mark.parametrize("computed_at", ["2026-09-07T01:25:00Z", "2026-09-07T07:30:00Z"])
def test_shadow_candidate_must_exist_before_first_session_auction(shadow_inputs, computed_at):
    binding, identity, proposal, _ = shadow_inputs
    proposal.computed_at = computed_at
    result = job._make_shadow_reader(binding, identity, REVISION)(proposal)
    assert result["status"] == "failed" and "observation" not in result



def test_native_diagnosis_pending_reads_original_task_without_new_request():
    from quant_platform_kit.strategy_lifecycle.ai_provider import AiServiceConfig, AiProviderConfig
    replies = [SimpleNamespace(success=False, raw={"status": "running", "id": "task-cn"}),
               SimpleNamespace(success=True, provider="dot", output='{"optimization_needed":false}',
                               raw={"status": "completed", "id": "task-cn", "result_kind": "advisory",
                                    "model_requested": "configured-dot", "model_verification": "unavailable"})]
    client = Mock()
    client.execute.side_effect = replies
    runtime = SimpleNamespace(client=lambda _: client, config=AiServiceConfig,
        route=SimpleNamespace(from_env=lambda: AiProviderConfig("primary", "agent", "configured-dot", "default")),
        cn=SimpleNamespace(BASELINE_PARAMS={}), context=lambda **kwargs: kwargs, prompt=lambda _: "frozen synthetic prompt")
    diagnosis = job._diagnosis(runtime, object(), REVISION)
    pending = diagnosis()
    assert pending == {"optimization_needed": False, "reason": "ai_task_pending", "task_id": "task-cn"}
    decision = diagnosis.read_pending(pending)
    assert decision["optimization_needed"] is False
    assert decision["model_verification"] == "unavailable"
    assert "model" not in decision
    first, second = client.execute.call_args_list
    assert first.kwargs["idempotency_key"] == second.kwargs["idempotency_key"]
    assert "resume_task_id" not in first.kwargs
    assert second.kwargs["resume_task_id"] == "task-cn"


@pytest.mark.parametrize("raw", [
    {"status": "completed", "id": "task", "result_kind": "execution"},
    {"status": "completed", "id": "", "result_kind": "advisory"},
    {"status": "succeeded", "id": "task", "result_kind": "advisory"},
])
def test_native_diagnosis_rejects_unbound_or_legacy_results(raw):
    from quant_platform_kit.strategy_lifecycle.ai_provider import AiServiceConfig, AiProviderConfig
    result = SimpleNamespace(success=True, provider="dot", raw=raw, output='{"optimization_needed":true,"recommended_method":"grid_search"}')
    runtime = SimpleNamespace(client=lambda _: SimpleNamespace(execute=lambda *a, **kw: result),
        config=AiServiceConfig, route=SimpleNamespace(from_env=lambda: AiProviderConfig("primary", "agent", "configured-dot", "default")),
        cn=SimpleNamespace(BASELINE_PARAMS={}), context=lambda **kwargs: kwargs, prompt=lambda _: "synthetic")
    with pytest.raises(ValueError, match="outcome_unavailable"):
        job._diagnosis(runtime, object(), REVISION)()
