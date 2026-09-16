from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round12 as round12,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_live_verifier as live_verifier,
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

    report = (
        output
        / "typed-research-run"
        / "actions"
        / "action-1"
        / "action_result.json"
    )
    report.parent.mkdir(parents=True)
    report.write_bytes(b'{"execution_status":"completed"}\n')
    action = {
        "action_id": "action-1",
        "artifacts": [
            {
                "path": str(report),
                "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                "bytes": report.stat().st_size,
            }
        ],
    }
    qualification = {
        "source_config_path": str(source),
        "policy_sha256": "p" * 64,
    }
    source_manifest = {
        "schema_version": "test",
        "manifest_sha256": "s" * 64,
    }
    persisted = {
        "standing-network-policy-qualification.json": qualification,
        "source-readme-manifest.json": source_manifest,
        "typed-execution-handoff.json": {"research_ledger_sha256": "e" * 64},
    }
    manifest = {
        "cycles": [
            {
                "network_policy_sha256": "p" * 64,
                "typed_request_sha256": "q" * 64,
                "pre_execution_ledger_sha256": "e" * 64,
            }
        ]
    }

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
    monkeypatch.setattr(
        round12._round11,
        "_find_request_by_sha",
        lambda *_args: request_path,
    )
    monkeypatch.setattr(
        round12,
        "load_research_state",
        lambda _run: {"actions": [copy.deepcopy(action)]},
    )
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["request"]["action_id"] = "forged-action"
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="action_id drifted",
    ):
        round12._verify_cycle1_independent_bindings(
            fixture["output"], fixture["manifest"]
        )


def test_cycle1_action_report_bytes_must_match_ledger_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["report"].write_bytes(b'{"scientific_status_changed":true}\n')
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="bytes drifted",
    ):
        round12._verify_cycle1_independent_bindings(
            fixture["output"], fixture["manifest"]
        )


def test_cycle1_network_policy_digest_is_independently_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["manifest"]["cycles"][0]["network_policy_sha256"] = "x" * 64
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="policy digest drifted",
    ):
        round12._verify_cycle1_independent_bindings(
            fixture["output"], fixture["manifest"]
        )


def test_cycle1_readme_manifest_is_replayed_from_retained_source_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["persisted"]["source-readme-manifest.json"] = {
        "manifest_sha256": "forged"
    }
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="README manifest drifted",
    ):
        round12._verify_cycle1_independent_bindings(
            fixture["output"], fixture["manifest"]
        )


def test_cycle1_preexecution_digest_is_derived_from_retained_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _cycle1_fixture(tmp_path, monkeypatch)
    fixture["manifest"]["cycles"][0]["pre_execution_ledger_sha256"] = "f" * 64
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="pre-execution ledger digest drifted",
    ):
        round12._verify_cycle1_independent_bindings(
            fixture["output"], fixture["manifest"]
        )


def test_cycle8_original_no_candidate_resolution_is_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        round12._round11._round6,
        "_PROMOTIONS",
        (
            ("", "a1", "i1", 6, None),
            ("-2", "a2", "i2", 8, None),
            ("-3", "a3", "i3", 10, None),
        ),
    )
    monkeypatch.setattr(
        round12._round11._round7,
        "_canonical_gap_and_specification",
        lambda **_kwargs: ({}, {"requested_action_class": "a3"}, {}),
    )
    expected = {
        "resolution_status": "no_bounded_candidate_available",
        "candidate": None,
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
    }
    persisted = dict(expected)
    persisted["unrestricted_discovery_performed"] = True
    monkeypatch.setattr(
        round12,
        "resolve_or_discover_capability",
        lambda **_kwargs: copy.deepcopy(expected),
    )
    monkeypatch.setattr(
        round12._merge_gate,
        "_load",
        lambda _root, _name: copy.deepcopy(persisted),
    )
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="resolution-3 drifted",
    ):
        round12._verify_original_cycle8_resolution(
            tmp_path,
            {"cycles": [{} for _ in range(8)]},
            {2: {"registry_after": {"trusted": True}}},
        )


def test_cycle7_projection_rejects_unrestricted_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        round12._round11._round6,
        "_PROMOTIONS",
        (("", "bridge", "i1", 6, None), ("-2", "discovery", "i2", 8, None)),
    )
    artifacts = {
        "capability-gap.json": {
            "gap_class": "g1",
            "capability_gap_sha256_without_self_field": "1" * 64,
        },
        "capability-specification.json": {
            "capability_specification_sha256_without_self_field": "2" * 64
        },
        "capability-resolution.json": {
            "resolution_status": "bounded_candidate_discovered",
            "candidate": {},
        },
        "capability-gap-2.json": {
            "gap_class": "g2",
            "capability_gap_sha256_without_self_field": "3" * 64,
        },
        "capability-specification-2.json": {
            "capability_specification_sha256_without_self_field": "4" * 64
        },
        "capability-resolution-2.json": {
            "resolution_status": "bounded_candidate_discovered",
            "candidate": {
                "capability_candidate_sha256_without_self_field": "5" * 64
            },
        },
    }
    monkeypatch.setattr(
        round12._merge_gate,
        "_load",
        lambda _root, name: copy.deepcopy(artifacts[name]),
    )
    cycles: list[dict[str, Any]] = [
        {},
        {},
        {},
        {"cycle_sha256": "a" * 64},
        {},
        {"cycle_sha256": "b" * 64},
        {},
    ]
    cycle5 = {
        "cycle_index": 5,
        "predecessor_cycle_sha256": "a" * 64,
        "input_blocker": "experiment_specific_calibration_protocol_bridge_not_established",
        "selected_action_class": "bridge",
        "capability_available": False,
        "capability_gap_class": "g1",
        "capability_gap_sha256": "1" * 64,
        "capability_specification_sha256": "2" * 64,
        "resolution_status": "bounded_candidate_discovered",
        "bounded_candidate_discovered": True,
        "unrestricted_discovery_performed": False,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle5["cycle_sha256"] = round12._canonical_sha(cycle5)
    cycles[4] = cycle5
    cycle7 = {
        "cycle_index": 7,
        "predecessor_cycle_sha256": "b" * 64,
        "input_blocker": "experiment_specific_calibration_record_not_discovered",
        "selected_action_class": "discovery",
        "capability_available": False,
        "capability_gap_class": "g2",
        "capability_gap_sha256": "3" * 64,
        "capability_specification_sha256": "4" * 64,
        "resolution_status": "bounded_candidate_discovered",
        "bounded_candidate_discovered": True,
        "capability_candidate_sha256": "5" * 64,
        "unrestricted_discovery_performed": True,
        "arbitrary_code_generation_performed": False,
        "global_evidence_unavailability_claimed": False,
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle7["cycle_sha256"] = round12._canonical_sha(cycle7)
    cycles[6] = cycle7
    with pytest.raises(
        round12.AutonomousProductionFreshReviewRound12Error,
        match="cycle 7 projection drifted",
    ):
        round12._verify_discovery_cycle_projections(
            tmp_path, {"cycles": cycles}, {}
        )


@pytest.mark.parametrize(
    ("cycle_count", "expected_calls"),
    ((9, 0), (10, 1), (11, 1), (12, 1)),
)
def test_derived_artifact_replay_starts_at_cycle10(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cycle_count: int,
    expected_calls: int,
) -> None:
    manifest = {"cycles": [{} for _ in range(cycle_count)]}
    monkeypatch.setattr(
        round12._merge_gate,
        "_load",
        lambda _root, _name: copy.deepcopy(manifest),
    )
    monkeypatch.setattr(
        round12, "_verify_cycle1_independent_bindings", lambda *_args: None
    )
    monkeypatch.setattr(
        round12._round11, "_strict_replay_promotions", lambda *_args: {}
    )
    monkeypatch.setattr(
        round12, "_verify_original_cycle8_resolution", lambda *_args: None
    )
    monkeypatch.setattr(
        round12, "_verify_discovery_cycle_projections", lambda *_args: None
    )
    calls: list[int] = []
    monkeypatch.setattr(
        round12._round10,
        "_verify_derived_authorization_and_bridge_assessment",
        lambda *_args: calls.append(cycle_count),
    )
    round12.verify_fresh_review_round12_boundaries(tmp_path)
    assert len(calls) == expected_calls


def _exact_transport_stop_manifest() -> dict[str, Any]:
    return {
        "cycles": [
            {},
            {},
            {
                "cycle_index": 3,
                "selected_action_class": live_verifier.NIST_ACTION_CLASS,
                "scientific_status_changed": False,
            },
        ],
        "stop": {
            "status": "stopped",
            "reason_code": live_verifier.TRANSPORT_STOP_REASON_CODE,
            "requested_action_class": live_verifier.NIST_ACTION_CLASS,
            "scientific_status_changed": False,
        },
        "scientific_status_changed": False,
    }


def test_round12_skip_is_limited_to_exact_three_cycle_transport_stop() -> None:
    manifest = _exact_transport_stop_manifest()
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(manifest) is True

    wrong_reason = copy.deepcopy(manifest)
    wrong_reason["stop"]["reason_code"] = "maximum_cycles_reached"
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(wrong_reason) is False

    wrong_action = copy.deepcopy(manifest)
    wrong_action["cycles"][2]["selected_action_class"] = "external_evidence_search"
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(wrong_action) is False

    widened_science = copy.deepcopy(manifest)
    widened_science["scientific_status_changed"] = True
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(widened_science) is False


def test_current_output_cannot_delete_round12_fields_and_claim_transport_skip() -> None:
    manifest = _exact_transport_stop_manifest()
    manifest["cycles"].append({"cycle_index": 4})
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(manifest) is False

    manifest = _exact_transport_stop_manifest()
    manifest["stop"].pop("requested_action_class")
    assert live_verifier._is_exact_nist_transport_stop_lifecycle(manifest) is False


def test_round12_is_wired_and_uploaded_by_the_live_gate() -> None:
    module_root = Path(round12.__file__).resolve().parent
    verifier = (module_root / "autonomous_production_live_verifier.py").read_text(
        encoding="utf-8"
    )
    workflow = (
        module_root.parents[2]
        / ".github"
        / "workflows"
        / "autonomous-production-live.yml"
    ).read_text(encoding="utf-8")
    assert "verify_fresh_review_round12_boundaries(root)" in verifier
    assert "tests/test_autonomous_production_fresh_review_round12.py" in workflow
    assert "standing-network-policy-qualification.json" in workflow
