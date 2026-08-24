from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_live_verifier as live_verifier
from materials_data_analyzer.research_loop import autonomous_production_transport_recovery as recovery
from materials_data_analyzer.research_loop.nist_mds2_2923_production_acquisition import (
    NistMds22923ProductionAcquisitionError,
    NistMds22923ProductionTransportError,
)

MISSION_SHA = "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
NIST_POLICY_SHA = "4b19c64f4f2c764f5315971c5afba16000763a4d307929ec5e463f42ee1cbebf"


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
            "selected_action_class": "external_evidence_search",
            "output_blocker": "cross_source_physical_comparability_not_established",
            "output_next_action_class": "reviewed_physical_comparability_assessment",
            "new_verified_information": True,
            "scientific_status_changed": False,
        },
        "cycle_sha256",
    )
    cycle2 = _hashed(
        {
            "cycle_index": 2,
            "predecessor_cycle_sha256": cycle1["cycle_sha256"],
            "selected_action_class": "reviewed_physical_comparability_assessment",
            "direct_nist_condition_comparability_established": False,
            "numerical_cross_source_validation_authorized": False,
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
            "mission_id": "autonomous-in625-production-v1",
            "mission_sha256": MISSION_SHA,
            "production_profile": "in625_zenodo_20503603_first_real_closed_loop",
            "measurement_row_count": 200289,
            "complete_numeric_measurement_row_count": 200288,
            "incomplete_numeric_measurement_row_count": 1,
            "parallel_test_block_count": 19,
            "caller_authored_request_queue_used": False,
            "machine_authored_typed_request_used": True,
            "unrestricted_network_search_performed": False,
            "arbitrary_command_execution_performed": False,
            "missing_value_imputation_performed": False,
            "row_exclusion_performed": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "numerical_cross_source_comparison_performed": False,
            "numerical_cross_source_validation_authorized": False,
            "direct_nist_condition_comparability_established": False,
            "response_compatible_geometry_evidence_acquired": False,
            "paper_evidence_promoted_to_row_level_authority": False,
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
            "positive_scientific_closeout_established": False,
            "scientific_status_changed": False,
        },
        "manifest_sha256",
    )
    _write_json(output / "autonomous-production-manifest.json", manifest)

    qualification = {
        "schema_version": "1.0",
        "qualification_status": "exact_nist_mds2_2923_network_policy_authenticated",
        "mission_sha256": MISSION_SHA,
        "policy_id": recovery.NIST_POLICY_ID,
        "policy_sha256": NIST_POLICY_SHA,
        "action_class": recovery.NIST_ACTION_CLASS,
        "candidate_id": recovery.NIST_CANDIDATE_ID,
        "product_id": recovery.NIST_PRODUCT_ID,
        "network_access_performed": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "scientific_status_changed": False,
    }
    _write_json(output / "nist-network-policy-qualification.json", qualification)

    authorization = {
        "schema_version": "1.0",
        "authorization_status": "authorized_exact_nist_mds2_2923_acquisition",
        "mission_sha256": MISSION_SHA,
        "policy_id": recovery.NIST_POLICY_ID,
        "policy_sha256": qualification["policy_sha256"],
        "action_class": recovery.NIST_ACTION_CLASS,
        "candidate_id": recovery.NIST_CANDIDATE_ID,
        "product_id": recovery.NIST_PRODUCT_ID,
        "network_access_performed": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "caller_authored_url_used": False,
        "caller_authored_file_queue_used": False,
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


def _rehash_report_cycle_manifest(
    output: Path,
    mutate_report: Any | None = None,
    mutate_cycle: Any | None = None,
    mutate_manifest: Any | None = None,
) -> None:
    report_path = output / "nist-transport-unavailability.json"
    manifest_path = output / "autonomous-production-manifest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    report.pop("report_sha256_without_self_field", None)
    if mutate_report is not None:
        mutate_report(report)
    report_sha = recovery._canonical_sha(report)
    report["report_sha256_without_self_field"] = report_sha

    cycle3 = dict(manifest["cycles"][-1])
    cycle3.pop("cycle_sha256", None)
    cycle3["transport_unavailability_sha256"] = report_sha
    if mutate_cycle is not None:
        mutate_cycle(cycle3)
    cycle3["cycle_sha256"] = recovery._canonical_sha(cycle3)
    manifest["cycles"][-1] = cycle3
    manifest["nist_mds2_2923_transport_unavailability_sha256"] = report_sha
    manifest.pop("manifest_sha256", None)
    if mutate_manifest is not None:
        mutate_manifest(manifest)
    manifest["manifest_sha256"] = recovery._canonical_sha(manifest)

    _write_json(report_path, report)
    _write_json(manifest_path, manifest)


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
    assert (
        live_verifier.verify_live_autonomous_output(output)
        == "typed_nist_transport_stop_verified"
    )


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


def test_live_verifier_rejects_rehashed_report_with_stale_manifest_cycle_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    report_path = output / "nist-transport-unavailability.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("report_sha256_without_self_field")
    report["transport_exception_message"] = "mutated but self-hashed report"
    report["report_sha256_without_self_field"] = recovery._canonical_sha(report)
    _write_json(report_path, report)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="transport report.*binding",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_live_verifier_rejects_rehashed_authorization_that_widens_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    auth_path = output / "nist-network-authorization.json"
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization.pop("authorization_sha256")
    authorization["caller_authored_url_used"] = True
    authorization_sha = recovery._canonical_sha(authorization)
    authorization["authorization_sha256"] = authorization_sha
    _write_json(auth_path, authorization)

    def mutate_report(report: dict[str, Any]) -> None:
        report["authorization_sha256"] = authorization_sha

    def mutate_cycle(cycle: dict[str, Any]) -> None:
        cycle["network_authorization_sha256"] = authorization_sha

    def mutate_manifest(manifest: dict[str, Any]) -> None:
        manifest["nist_mds2_2923_network_authorization_sha256"] = authorization_sha

    _rehash_report_cycle_manifest(output, mutate_report, mutate_cycle, mutate_manifest)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="authorization widened authority",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_live_verifier_rejects_bounded_stop_manifest_divergence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    stop_path = output / "bounded-stop.json"
    stop = json.loads(stop_path.read_text(encoding="utf-8"))
    stop["candidate_id"] = "different-candidate"
    _write_json(stop_path, stop)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="bounded-stop artifact does not match manifest stop",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_live_verifier_rejects_consistently_rehashed_nontransport_exception_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    _rehash_report_cycle_manifest(
        output,
        mutate_report=lambda report: report.__setitem__(
            "transport_exception_type", "NistMds22923ProductionAcquisitionError"
        ),
    )

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="typed transient exception",
    ):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("row_exclusion_performed", True),
        ("direct_numerical_cross_source_validation_authorized", True),
        ("bridge_established", True),
        ("directly_comparable_mds2_rows", 1),
    ],
)
def test_live_verifier_rejects_rehashed_pretransport_scientific_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    manifest_path = output / "autonomous-production-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("manifest_sha256")
    manifest[field] = value
    manifest["manifest_sha256"] = recovery._canonical_sha(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize("status", [404, 410])
def test_permanent_http_resource_failure_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: int,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    def fail_permanent_http(**_: object) -> dict[str, Any]:
        raise NistMds22923ProductionAcquisitionError(
            f"NIST exact artifact acquisition failed: HTTP acquisition failed: {status}"
        )

    monkeypatch.setattr(recovery, "run_reference_chain_production", fail_permanent_http)

    with pytest.raises(
        NistMds22923ProductionAcquisitionError,
        match=rf"HTTP acquisition failed: {status}",
    ):
        recovery.run_autonomous_production(
            repository_root=root,
            mission_path=root / "unused-mission.json",
            expected_mission_sha256="0" * 64,
            output_root="outputs/run",
            max_cycles=12,
        )


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
