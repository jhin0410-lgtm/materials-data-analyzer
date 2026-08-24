from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_transport_recovery as recovery
from materials_data_analyzer.research_loop.nist_mds2_2923_production_acquisition import (
    NistMds22923ProductionAcquisitionError,
    NistMds22923ProductionTransportError,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = recovery._canonical_sha(result)
    return result


def _prepare_pretransport_state(
    root: Path,
    output_root: str | Path,
    *,
    persist_partial_nist_bytes: bool = True,
) -> Path:
    output = Path(output_root)
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True)

    cycle1 = _hashed(
        {
            "cycle_index": 1,
            "new_verified_information": True,
            "scientific_status_changed": False,
        },
        "cycle_sha256",
    )
    cycle2 = _hashed(
        {
            "cycle_index": 2,
            "predecessor_cycle_sha256": cycle1["cycle_sha256"],
            "output_blocker": "response_compatible_geometry_evidence_not_acquired",
            "output_next_action_class": recovery.NIST_ACTION_CLASS,
            "new_verified_information": True,
            "scientific_status_changed": False,
        },
        "cycle_sha256",
    )
    manifest = _hashed(
        {
            "schema_version": "1.1",
            "policy_version": "1.1",
            "cycles": [cycle1, cycle2],
            "stop": {
                "status": "stopped",
                "reason_code": "maximum_cycles_reached",
                "requested_action_class": recovery.NIST_ACTION_CLASS,
                "scientific_status_changed": False,
            },
            "preferred_geometry_candidate_id": recovery.NIST_CANDIDATE_ID,
            "final_blocker": "response_compatible_geometry_evidence_not_acquired",
            "generated_next_action_class": recovery.NIST_ACTION_CLASS,
            "global_evidence_unavailability_claimed": False,
            "scientific_status_changed": False,
        },
        "manifest_sha256",
    )
    _write_json(output / "autonomous-production-manifest.json", manifest)

    qualification = {
        "qualification_status": "exact_nist_mds2_2923_network_policy_authenticated",
        "policy_id": recovery.NIST_POLICY_ID,
        "policy_sha256": "a" * 64,
        "action_class": recovery.NIST_ACTION_CLASS,
        "candidate_id": recovery.NIST_CANDIDATE_ID,
        "product_id": recovery.NIST_PRODUCT_ID,
        "network_access_performed": False,
    }
    _write_json(output / "nist-network-policy-qualification.json", qualification)

    authorization = {
        "authorization_status": "authorized_exact_nist_mds2_2923_acquisition",
        "policy_id": recovery.NIST_POLICY_ID,
        "policy_sha256": qualification["policy_sha256"],
        "action_class": recovery.NIST_ACTION_CLASS,
        "candidate_id": recovery.NIST_CANDIDATE_ID,
        "product_id": recovery.NIST_PRODUCT_ID,
        "network_access_performed": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "scientific_status_changed": False,
    }
    authorization["authorization_sha256"] = recovery._canonical_sha(authorization)
    _write_json(output / "nist-network-authorization.json", authorization)

    partial = output / "nist-mds2-2923"
    partial.mkdir()
    if persist_partial_nist_bytes:
        (partial / "nerdm-metadata.json").write_bytes(
            b"partial authenticated metadata fixture"
        )
    return output


def test_success_path_is_exact_pass_through(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    expected = {"status": "full-reference-chain-success"}

    monkeypatch.setattr(
        recovery,
        "run_reference_chain_production",
        lambda **_: expected,
    )

    result = recovery.run_autonomous_production(
        repository_root=root,
        mission_path=root / "unused-mission.json",
        expected_mission_sha256="0" * 64,
        output_root="outputs/run",
        max_cycles=12,
    )

    assert result is expected


def _run_transport_stop(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root: Path,
) -> dict[str, Any]:
    def fail_transport(**_: object) -> dict[str, Any]:
        raise NistMds22923ProductionTransportError(
            "NIST exact artifact transport failed for 2923_README.txt: HTTP acquisition failed: 524"
        )

    monkeypatch.setattr(recovery, "run_reference_chain_production", fail_transport)
    return recovery.run_autonomous_production(
        repository_root=root,
        mission_path=root / "unused-mission.json",
        expected_mission_sha256="0" * 64,
        output_root="outputs/run",
        max_cycles=12,
    )


def test_typed_nist_transport_failure_becomes_self_hashed_bounded_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")

    result = _run_transport_stop(monkeypatch, root=root)

    assert result["stop"]["reason_code"] == recovery.TRANSPORT_STOP_REASON_CODE
    assert result["stop"]["retry_performed"] is False
    assert result["stop"]["retry_authorized_within_current_request_budget"] is False
    assert result["stop"]["global_evidence_unavailability_claimed"] is False
    assert result["stop"]["network_failure_interpreted_as_negative_scientific_evidence"] is False
    assert result["stop"]["alternative_evidence_lanes_remain_allowed"] is True
    assert result["generated_next_action_class"] == recovery.NIST_ACTION_CLASS
    assert result["response_compatible_geometry_evidence_acquired"] is False
    assert result["nist_mds2_2923_acquisition_completed"] is False
    assert result["nist_mds2_2923_scientific_intake_performed"] is False
    assert result["scientific_status_changed"] is False
    assert len(result["cycles"]) == 3
    cycle3 = result["cycles"][-1]
    assert cycle3["acquisition_completed"] is False
    assert cycle3["retry_performed"] is False
    assert cycle3["new_verified_operational_information"] is True
    assert cycle3["new_verified_scientific_information"] is False
    unsigned_cycle = dict(cycle3)
    cycle_sha = unsigned_cycle.pop("cycle_sha256")
    assert recovery._canonical_sha(unsigned_cycle) == cycle_sha

    persisted = json.loads(
        (output / "autonomous-production-manifest.json").read_text(encoding="utf-8")
    )
    unsigned_manifest = dict(persisted)
    manifest_sha = unsigned_manifest.pop("manifest_sha256")
    assert recovery._canonical_sha(unsigned_manifest) == manifest_sha
    assert persisted == result

    report = json.loads(
        (output / "nist-transport-unavailability.json").read_text(encoding="utf-8")
    )
    report_sha = report.pop("report_sha256_without_self_field")
    assert recovery._canonical_sha(report) == report_sha
    assert report["partial_output_present"] is True
    assert report["partial_output_reuse_authorized"] is False
    assert report["retry_performed"] is False
    assert report["network_request_budget_widened"] is False
    assert report["allowed_hosts_widened"] is False
    assert report["alternate_url_synthesized"] is False
    assert report["scientific_intake_performed"] is False
    assert not (output / "nist-scientific-intake.json").exists()
    assert not (output / "nist-network-acquisition-receipt.json").exists()


def test_empty_nist_output_directory_is_not_reported_as_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(
        root,
        "outputs/run",
        persist_partial_nist_bytes=False,
    )

    result = _run_transport_stop(monkeypatch, root=root)

    report = json.loads(
        (output / "nist-transport-unavailability.json").read_text(encoding="utf-8")
    )
    assert report["partial_output_present"] is False
    assert report["partial_output_reuse_authorized"] is False
    assert result["nist_mds2_2923_acquisition_completed"] is False
    assert result["nist_mds2_2923_scientific_intake_performed"] is False


def test_non_transport_nist_acquisition_error_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    def fail_integrity(**_: object) -> dict[str, Any]:
        raise NistMds22923ProductionAcquisitionError("checksum mismatch")

    monkeypatch.setattr(recovery, "run_reference_chain_production", fail_integrity)

    with pytest.raises(NistMds22923ProductionAcquisitionError, match="checksum mismatch"):
        recovery.run_autonomous_production(
            repository_root=root,
            mission_path=root / "unused-mission.json",
            expected_mission_sha256="0" * 64,
            output_root="outputs/run",
            max_cycles=12,
        )
