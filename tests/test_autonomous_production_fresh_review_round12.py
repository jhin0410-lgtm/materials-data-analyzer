from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round12 as round12,
)


def _cycle1_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    repository = tmp_path / "repository"
    output = repository / "outputs" / "autonomous-in625-production"
    output.mkdir(parents=True)
    source = repository / round12._round11._SOURCE_CONFIG_PATH
    policy = repository / round12._NETWORK_POLICY_PATH
    registry = repository / round12._round11._ACTION_REGISTRY_PATH
    mission = repository / "mission.json"
    for path in (source, policy, registry, mission):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    readme_name = "README - Dataset description.txt"
    (output / "record.json").write_bytes(b"metadata")
    (output / readme_name).write_bytes(b"readme")
    request_path = output / "machine-authored-request" / "request.json"
    request_path.parent.mkdir(parents=True)
    request_path.write_text("{}\n", encoding="utf-8")
    request = {"action_id": "action-1"}

    report = output / "typed-research-run" / "actions" / "action-1" / "action_result.json"
    report.parent.mkdir(parents=True)
    report.write_bytes(b'{"execution_status":"completed"}\n')
    action = {
        "action_id": "action-1",
        "artifacts": [{
            "path": str(report),
            "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "bytes": report.stat().st_size,
        }],
    }
    qualification = {"source_config_path": str(source), "policy_sha256": "p" * 64}
    source_manifest = {"schema_version": "test", "manifest_sha256": "s" * 64}
    persisted = {
        "standing-network-policy-qualification.json": qualification,
        "source-readme-manifest.json": source_manifest,
        "typed-execution-handoff.json": {"research_ledger_sha256": "e" * 64},
    }
    manifest = {"cycles": [{
        "network_policy_sha256": "p" * 64,
        "typed_request_sha256": "q" * 64,
        "pre_execution_ledger_sha256": "e" * 64,
    }]}

    monkeypatch.setattr(
        round12._round11._round7,
        "_trusted_mission_binding",
        lambda: (repository, mission, "m" * 64),
    )
    monkeypatch.setattr(
        round12,
        "authenticate_in625_network_policy",
        lambda **_kwargs: copy.deepcopy(qualification),
    )

    def load_plain(path: Path, *, label: str) -> dict[str, Any]:
        del label
        if Path(path) == source:
            return {"zenodo": {"readme_file": readme_name}}
        return copy.deepcopy(request)

    monkeypatch.setattr(round12._round11, "_load_plain_json", load_plain)
    monkeypatch.setattr(
        round12,
        "build_verified_in625_zenodo_readme_manifest",
        lambda **_kwargs: copy.deepcopy(source_manifest),
    )
    monkeypatch.setattr(round12._round11, "_find_request_by_sha", lambda *_args: request_path)
    monkeypatch.setattr(round12, "load_research_state", lambda _run: {"actions": [copy.deepcopy(action)]})
    monkeypatch.setattr(
        round12,
        "verify_preexecution_authorization",
        lambda **_kwargs: {"pre_execution_ledger_sha256": "e" * 64},
    )
    monkeypatch.setattr(
        round12._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(persisted[name]),
    )
    return {
        "output": output,
        "request": request,
        "report": report,
        "manifest": manifest,
        "persisted": persisted,
    }


def test_cycle1_request_action_id_must_match_immutable_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["request"]["action_id"] = "forged-action"
    with pytest.raises(round12.AutonomousProductionFreshReviewRound12Error, match="action_id drifted"):
        round12._verify_cycle1_independent_bindings(fixture["output"], fixture["manifest"])


def test_cycle1_action_report_bytes_must_match_ledger_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["report"].write_bytes(b'{"scientific_status_changed":true}\n')
    with pytest.raises(round12.AutonomousProductionFreshReviewRound12Error, match="bytes drifted"):
        round12._verify_cycle1_independent_bindings(fixture["output"], fixture["manifest"])


def test_cycle1_network_policy_digest_is_independently_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["manifest"]["cycles"][0]["network_policy_sha256"] = "x" * 64
    with pytest.raises(round12.AutonomousProductionFreshReviewRound12Error, match="policy digest drifted"):
        round12._verify_cycle1_independent_bindings(fixture["output"], fixture["manifest"])


def test_cycle1_readme_manifest_is_replayed_from_retained_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["persisted"]["source-readme-manifest.json"] = {"manifest_sha256": "forged"}
    with pytest.raises(round12.AutonomousProductionFreshReviewRound12Error, match="README manifest drifted"):
        round12._verify_cycle1_independent_bindings(fixture["output"], fixture["manifest"])


def test_cycle1_preexecution_digest_is_derived_from_retained_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["manifest"]["cycles"][0]["pre_execution_ledger_sha256"] = "f" * 64
    with pytest.raises(round12.AutonomousProductionFreshReviewRound12Error, match="pre-execution ledger digest drifted"):
        round12._verify_cycle1_independent_bindings(fixture["output"], fixture["manifest"])


def test_round12_is_wired_and_uploaded_by_the_live_gate() -> None:
    module_root = Path(round12.__file__).resolve().parent
    verifier = (module_root / "autonomous_production_live_verifier.py").read_text(encoding="utf-8")
    workflow = (module_root.parents[2] / ".github" / "workflows" / "autonomous-production-live.yml").read_text(encoding="utf-8")
    assert "verify_fresh_review_round12_boundaries(root)" in verifier
    assert "tests/test_autonomous_production_fresh_review_round12.py" in workflow
    assert "standing-network-policy-qualification.json" in workflow
