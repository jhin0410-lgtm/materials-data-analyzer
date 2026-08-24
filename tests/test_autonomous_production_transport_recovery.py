from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_live_verifier as live_verifier
from materials_data_analyzer.research_loop import autonomous_production_transport_recovery as recovery
from materials_data_analyzer.research_loop.nist_mds2_2923_network_policy import (
    ARTIFACT_ALLOWED_HOSTS,
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    MAX_ARTIFACT_BYTES,
    MAX_METADATA_BYTES,
    MAX_NETWORK_REQUESTS,
    MAX_TOTAL_ARTIFACT_BYTES,
    METADATA_ALLOWED_HOSTS,
    METADATA_ENDPOINT,
    TIMEOUT_SECONDS,
)
from materials_data_analyzer.research_loop.nist_mds2_2923_production_acquisition import (
    NistMds22923ProductionAcquisitionError,
    NistMds22923ProductionTransportError,
)

MISSION_SHA = "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
NIST_POLICY_SHA = "4b19c64f4f2c764f5315971c5afba16000763a4d307929ec5e463f42ee1cbebf"
ZENODO_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
ZENODO_ARCHIVE_SHA = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
COMPARABILITY_DECISION = (
    "direct_nist_numerical_validation_blocked_by_response_and_protocol_incompatibility"
)
EXPECTED_NIST_FILES = {
    path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()
}


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


def _comparability_fixture() -> dict[str, Any]:
    return _hashed(
        {
            "schema_version": "1.0",
            "policy_version": "1.0",
            "action_class": "reviewed_physical_comparability_assessment",
            "assessment_status": "reviewed_comparability_assessed_direct_validation_blocked",
            "gate_decision": {
                "decision_code": COMPARABILITY_DECISION,
                "direct_nist_condition_comparability_established": False,
                "numerical_cross_source_validation_authorized": False,
                "scalar_residual_comparison_authorized": False,
                "empirical_model_validation_established": False,
                "hypothesis_truth_established": False,
                "scientific_status_changed": False,
            },
            "next_action": {
                "action_class": recovery.NIST_ACTION_CLASS,
                "candidate_id": recovery.NIST_CANDIDATE_ID,
                "direct_comparability_preestablished": False,
                "network_access_performed": False,
                "automatic_execution_authorized": False,
            },
            "scientific_boundary": {
                "numerical_cross_source_comparison_performed": False,
                "model_fit_performed": False,
                "empirical_model_validation_established": False,
                "hypothesis_truth_established": False,
                "positive_scientific_closeout_established": False,
                "global_evidence_unavailability_claimed": False,
                "automatic_scientific_promotion": False,
                "scientific_status_changed": False,
            },
        },
        "assessment_sha256",
    )


def _write_cycle1_evidence(output: Path) -> tuple[str, str, str]:
    receipt = _hashed(
        {
            "schema_version": "1.0",
            "policy_version": "1.0",
            "source_id": ZENODO_SOURCE_ID,
            "zenodo_record_id": "20503603",
            "archive": {"sha256": ZENODO_ARCHIVE_SHA},
            "network_access_performed": True,
            "network_execution_authorized": True,
            "provider_checksum_verified": True,
            "project_sha256_verified": True,
            "byte_count_verified": True,
            "exact_host_restriction_enforced": True,
            "scientific_boundary": {
                "automatic_scientific_promotion": False,
                "direct_nist_condition_comparability_established": False,
                "empirical_model_validation_established": False,
                "hypothesis_truth_established": False,
                "positive_scientific_closeout_established": False,
            },
        },
        "receipt_sha256",
    )
    quality = _hashed(
        {
            "schema_version": "1.0",
            "quality_status": "verified_observed_source_quality",
            "source_id": ZENODO_SOURCE_ID,
            "source_archive_sha256": ZENODO_ARCHIVE_SHA,
            "measurement_row_count": 200289,
            "complete_numeric_measurement_row_count": 200288,
            "incomplete_numeric_measurement_row_count": 1,
            "missing_value_imputation_authorized": False,
            "row_exclusion_authorized": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "scientific_status_changed": False,
        },
        "verification_sha256",
    )
    rediagnosis = _hashed(
        {
            "schema_version": "2.0",
            "policy_version": "2.0",
            "current_blocker": {
                "code": "cross_source_physical_comparability_not_established"
            },
            "next_action": {
                "action_class": "reviewed_physical_comparability_assessment"
            },
            "stop_state": {"positive_scientific_closeout": False},
            "scientific_status_changed": False,
        },
        "rediagnosis_sha256",
    )
    _write_json(output / "network-acquisition-receipt.json", receipt)
    _write_json(output / "tensile-quality-verification.json", quality)
    _write_json(output / "quality-aware-rediagnosis.json", rediagnosis)
    return (
        receipt["receipt_sha256"],
        quality["verification_sha256"],
        rediagnosis["rediagnosis_sha256"],
    )


def _finite_network_fields() -> dict[str, Any]:
    return {
        "metadata_endpoint": METADATA_ENDPOINT,
        "expected_nerdm_metadata_sha256": EXPECTED_METADATA_SHA256,
        "expected_files": EXPECTED_NIST_FILES,
        "metadata_allowed_hosts": list(METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(ARTIFACT_ALLOWED_HOSTS),
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "maximum_metadata_bytes": MAX_METADATA_BYTES,
        "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
        "maximum_total_artifact_bytes": MAX_TOTAL_ARTIFACT_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
    }


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

    comparability = _comparability_fixture()
    _write_json(output / "physical-comparability-assessment.json", comparability)
    receipt_sha, quality_sha, rediagnosis_sha = _write_cycle1_evidence(output)

    cycle1 = _hashed(
        {
            "cycle_index": 1,
            "selected_action_class": "external_evidence_search",
            "network_receipt_sha256": receipt_sha,
            "quality_verification_sha256": quality_sha,
            "rediagnosis_sha256": rediagnosis_sha,
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
            "comparability_assessment_sha256": comparability["assessment_sha256"],
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
            "comparability_assessment_sha256": comparability["assessment_sha256"],
            "comparability_decision_code": COMPARABILITY_DECISION,
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
        **_finite_network_fields(),
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
        **_finite_network_fields(),
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


def _rehash_comparability_chain(output: Path, mutate_assessment: Any) -> None:
    assessment_path = output / "physical-comparability-assessment.json"
    manifest_path = output / "autonomous-production-manifest.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assessment.pop("assessment_sha256")
    mutate_assessment(assessment)
    assessment_sha = recovery._canonical_sha(assessment)
    assessment["assessment_sha256"] = assessment_sha

    cycle2 = dict(manifest["cycles"][1])
    cycle2.pop("cycle_sha256")
    cycle2["comparability_assessment_sha256"] = assessment_sha
    cycle2["cycle_sha256"] = recovery._canonical_sha(cycle2)
    manifest["cycles"][1] = cycle2

    cycle3 = dict(manifest["cycles"][2])
    cycle3.pop("cycle_sha256")
    cycle3["predecessor_cycle_sha256"] = cycle2["cycle_sha256"]
    cycle3["cycle_sha256"] = recovery._canonical_sha(cycle3)
    manifest["cycles"][2] = cycle3

    manifest["comparability_assessment_sha256"] = assessment_sha
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = recovery._canonical_sha(manifest)

    _write_json(assessment_path, assessment)
    _write_json(manifest_path, manifest)


def _rehash_authorization_chain(output: Path, mutate_authorization: Any) -> None:
    auth_path = output / "nist-network-authorization.json"
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization.pop("authorization_sha256")
    mutate_authorization(authorization)
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


def test_success_path_is_exact_pass_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    expected = {"status": "full-reference-chain-success"}
    monkeypatch.setattr(recovery, "run_reference_chain_production", lambda **_: expected)

    result = recovery.run_autonomous_production(
        repository_root=root,
        mission_path=root / "unused-mission.json",
        expected_mission_sha256="0" * 64,
        output_root="outputs/run",
        max_cycles=12,
    )
    assert result is expected


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
    _rehash_authorization_chain(
        output,
        lambda authorization: authorization.__setitem__("caller_authored_url_used", True),
    )

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="authorization widened authority",
    ):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_network_requests", 999),
        ("metadata_allowed_hosts", ["untrusted.example"]),
        ("artifact_allowed_hosts", ["untrusted.example"]),
        ("maximum_total_artifact_bytes", MAX_TOTAL_ARTIFACT_BYTES + 1),
        ("timeout_seconds", TIMEOUT_SECONDS + 1),
    ],
)
def test_live_verifier_rejects_rehashed_finite_network_authority_widening(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)
    _rehash_authorization_chain(
        output, lambda authorization: authorization.__setitem__(field, value)
    )

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
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
    "artifact_name",
    [
        "network-acquisition-receipt.json",
        "tensile-quality-verification.json",
        "quality-aware-rediagnosis.json",
    ],
)
def test_live_verifier_rejects_missing_cycle1_evidence_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    artifact_name: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)
    (output / artifact_name).unlink()

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


def test_live_verifier_rejects_rehashed_cycle1_quality_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    quality_path = output / "tensile-quality-verification.json"
    manifest_path = output / "autonomous-production-manifest.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quality.pop("verification_sha256")
    quality["positive_scientific_closeout_established"] = True
    quality_sha = recovery._canonical_sha(quality)
    quality["verification_sha256"] = quality_sha

    cycle1 = dict(manifest["cycles"][0])
    cycle1.pop("cycle_sha256")
    cycle1["quality_verification_sha256"] = quality_sha
    cycle1["cycle_sha256"] = recovery._canonical_sha(cycle1)
    manifest["cycles"][0] = cycle1

    cycle2 = dict(manifest["cycles"][1])
    cycle2.pop("cycle_sha256")
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["cycle_sha256"] = recovery._canonical_sha(cycle2)
    manifest["cycles"][1] = cycle2

    cycle3 = dict(manifest["cycles"][2])
    cycle3.pop("cycle_sha256")
    cycle3["predecessor_cycle_sha256"] = cycle2["cycle_sha256"]
    cycle3["cycle_sha256"] = recovery._canonical_sha(cycle3)
    manifest["cycles"][2] = cycle3
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = recovery._canonical_sha(manifest)
    _write_json(quality_path, quality)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="quality evidence scientific state drifted",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_live_verifier_rejects_missing_comparability_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)
    (output / "physical-comparability-assessment.json").unlink()

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize(
    "mutation",
    [
        "gate_authorization",
        "preestablished_comparability",
        "positive_closeout",
        "global_unavailability",
    ],
)
def test_live_verifier_rejects_rehashed_comparability_authority_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)

    def promote(assessment: dict[str, Any]) -> None:
        if mutation == "gate_authorization":
            assessment["gate_decision"]["numerical_cross_source_validation_authorized"] = True
        elif mutation == "preestablished_comparability":
            assessment["next_action"]["direct_comparability_preestablished"] = True
        elif mutation == "positive_closeout":
            assessment["scientific_boundary"]["positive_scientific_closeout_established"] = True
        else:
            assessment["scientific_boundary"]["global_evidence_unavailability_claimed"] = True

    _rehash_comparability_chain(output, promote)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("network_failure_interpreted_as_negative_scientific_evidence", True),
        ("output_blocker", "invented_scientific_blocker"),
        ("output_next_action_class", "invented_next_action"),
        ("new_verified_scientific_information", True),
    ],
)
def test_live_verifier_rejects_rehashed_cycle3_scientific_interpretation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    output = _prepare_pretransport_state(root, "outputs/run")
    _run_transport_stop(monkeypatch, root=root)
    _rehash_report_cycle_manifest(
        output, mutate_cycle=lambda cycle: cycle.__setitem__(field, value)
    )

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="transport cycle 3 scientific/operational contract drifted",
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
