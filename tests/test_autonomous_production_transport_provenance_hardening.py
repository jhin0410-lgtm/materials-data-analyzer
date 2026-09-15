from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_live_verifier as live_verifier
from materials_data_analyzer.research_loop import autonomous_production_semantic_hardening as semantic_hardening
from materials_data_analyzer.research_loop.nist_mds2_2923_network_policy import (
    EXPECTED_METADATA_SHA256,
)


_SOURCE_PATH = Path(__file__).with_name("test_autonomous_production_transport_recovery.py")
_SPEC = importlib.util.spec_from_file_location("_transport_fixture_source", _SOURCE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_source = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_source)
_base = _source._base

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_BINDING_PATHS = {
    "nist_planning_readiness": (
        "configs/research/nist_ambench_2018_02_planning_readiness.v1.json"
    ),
    "nist_process_conditions": (
        "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv"
    ),
    "nist_melt_pool_measurements": (
        "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv"
    ),
    "nist_case_readme": "data/case_studies/nist_ambench_2018_02/README.md",
    "zenodo_reviewed_tensile_contract": (
        "configs/research/in625_tensile_reviewed_intake.v1.json"
    ),
    "zenodo_verified_source": (
        "configs/research/in625_zenodo_20503603_verified_source.v1.json"
    ),
    "zenodo_observed_quality_contract": (
        "configs/research/in625_tensile_observed_quality.v1.json"
    ),
    "in625_physical_source_frontier": (
        "configs/research/in625_external_physical_source_frontier.v1.json"
    ),
}
_EXPECTED_INCOMPLETE_ROWS = _source._EXPECTED_INCOMPLETE_ROWS


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = _base.recovery._canonical_sha(value)


def _binding(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    raw = path.read_bytes()
    return {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _copy_repository_evidence(root: Path) -> None:
    for relative in _BINDING_PATHS.values():
        source = _REPOSITORY_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _prepare_hardened(root: Path) -> Path:
    _copy_repository_evidence(root)
    output = _source._prepare_pretransport_state(root, "outputs/run")

    quality = _read(output / "tensile-quality-verification.json")
    rediagnosis = _read(output / "quality-aware-rediagnosis.json")
    rediagnosis["secondary_blockers"] = [
        {
            "code": "reviewed_numeric_source_missingness_observed",
            "kind": "data_quality",
            "severity": "bounded",
            "measurement_row_count": 200289,
            "affected_row_count": 1,
            "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
            "blocks_external_evidence_availability": False,
            "blocks_unqualified_use_of_affected_load_value": True,
            "missingness_mechanism_established": False,
            "imputation_authorized": False,
            "row_exclusion_authorized": False,
            "scientific_status_changed": False,
        }
    ]
    _rehash(rediagnosis, "rediagnosis_sha256")
    _write(output / "quality-aware-rediagnosis.json", rediagnosis)

    assessment = _read(output / "physical-comparability-assessment.json")
    assessment["predecessor_rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    assessment["observed_quality_verification_sha256"] = quality[
        "verification_sha256"
    ]
    assessment["evidence_bindings"] = {
        name: _binding(root, relative)
        for name, relative in _BINDING_PATHS.items()
    }
    _rehash(assessment, "assessment_sha256")
    _write(output / "physical-comparability-assessment.json", assessment)

    manifest = _read(output / "autonomous-production-manifest.json")
    cycles = [dict(item) for item in manifest["cycles"]]
    cycle1, cycle2 = cycles
    cycle1["rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    _rehash(cycle1, "cycle_sha256")
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(cycle2, "cycle_sha256")
    manifest["cycles"] = [cycle1, cycle2]
    manifest["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(manifest, "manifest_sha256")
    _write(output / "autonomous-production-manifest.json", manifest)

    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read(qualification_path)
    frontier_path = root / _BINDING_PATHS["in625_physical_source_frontier"]
    qualification["identifier"] = "10.18434/mds2-2923"
    qualification["frontier_path"] = str(frontier_path.resolve(strict=True))
    qualification["frontier_sha256"] = hashlib.sha256(
        frontier_path.read_bytes()
    ).hexdigest()
    _rehash(qualification, "qualification_sha256")
    _write(qualification_path, qualification)
    return output


def _rehash_manifest_cycles(manifest: dict[str, Any]) -> None:
    cycles = [dict(item) for item in manifest["cycles"]]
    predecessor: str | None = None
    for cycle in cycles:
        cycle.pop("cycle_sha256", None)
        if predecessor is not None:
            cycle["predecessor_cycle_sha256"] = predecessor
        cycle["cycle_sha256"] = _base.recovery._canonical_sha(cycle)
        predecessor = cycle["cycle_sha256"]
    manifest["cycles"] = cycles
    _rehash(manifest, "manifest_sha256")


def test_rehashed_manifest_cycle_index_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _prepare_hardened(tmp_path)
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    manifest["cycles"][0]["cycle_index"] = 7
    _rehash_manifest_cycles(manifest)
    _write(manifest_path, manifest)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="cycle 1 index drifted",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_rehashed_qualification_frontier_sha_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _prepare_hardened(tmp_path)
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    path = output / "nist-network-policy-qualification.json"
    qualification = _read(path)
    qualification["frontier_sha256"] = "0" * 64
    _rehash(qualification, "qualification_sha256")
    _write(path, qualification)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="NIST qualification frontier SHA-256 mismatch",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_rehashed_secondary_blocker_cannot_authorize_imputation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _prepare_hardened(tmp_path)
    _base._run_transport_stop(monkeypatch, root=tmp_path)

    def mutate(value: dict[str, Any]) -> None:
        value["secondary_blockers"][0]["imputation_authorized"] = True

    _source._rehash_predecessor_chain(output, mutate_rediagnosis=mutate)
    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="rediagnosis secondary data-quality authority drifted",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_rehashed_comparability_binding_cannot_forge_repository_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _prepare_hardened(tmp_path)
    _base._run_transport_stop(monkeypatch, root=tmp_path)

    def mutate(value: dict[str, Any]) -> None:
        value["evidence_bindings"]["nist_case_readme"]["sha256"] = "0" * 64

    _source._rehash_predecessor_chain(output, mutate_assessment=mutate)
    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="physical comparability evidence binding nist_case_readme SHA-256 mismatch",
    ):
        live_verifier.verify_live_autonomous_output(output)


def _build_successful_nist_semantic_fixture(output: Path) -> None:
    authorization = _read(output / "nist-network-authorization.json")
    authorization_sha = authorization["authorization_sha256"]

    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "acquisition_status": "exact_nist_mds2_2923_source_files_acquired",
        "authorization_sha256": authorization_sha,
        "policy_id": _base.recovery.NIST_POLICY_ID,
        "action_class": _base.recovery.NIST_ACTION_CLASS,
        "candidate_id": _base.recovery.NIST_CANDIDATE_ID,
        "product_id": _base.recovery.NIST_PRODUCT_ID,
        "metadata_sha256": EXPECTED_METADATA_SHA256,
        "network_requests_performed": 3,
        "network_request_budget": 3,
        "caller_authored_url_used": False,
        "caller_authored_file_queue_used": False,
        "unrestricted_network_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "all_acquisition_provenance_authenticated": True,
        "requires_scientific_intake": True,
        "scientific_status_changed": False,
    }
    _rehash(receipt, "receipt_sha256")
    _write(output / "nist-network-acquisition-receipt.json", receipt)

    intake: dict[str, Any] = {"schema_version": "1.0", "fixture": "exact-chain-only"}
    _rehash(intake, "report_sha256_without_self_field")
    _write(output / "nist-scientific-intake.json", intake)

    rediagnosis: dict[str, Any] = {
        "schema_version": "1.0",
        "input_acquisition_receipt_sha256": receipt["receipt_sha256"],
        "input_scientific_intake_sha256": intake[
            "report_sha256_without_self_field"
        ],
        "current_blocker": {"code": "geometry_condition_mapping_not_established"},
        "next_action": {"action_class": "reviewed_geometry_condition_mapping_assessment"},
        "scientific_boundary": {
            "response_compatible_geometry_evidence_acquired": True,
            "direct_target_condition_comparability_established": False,
            "cross_machine_pooling_performed": False,
            "calibration_conversion_performed": False,
            "issue_76_eligible": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "global_evidence_unavailability_claimed": False,
            "scientific_status_changed": False,
        },
    }
    _rehash(rediagnosis, "rediagnosis_sha256")
    _write(output / "nist-post-acquisition-rediagnosis.json", rediagnosis)

    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    cycles = [dict(item) for item in manifest["cycles"]]
    cycle3: dict[str, Any] = {
        "cycle_index": 3,
        "predecessor_cycle_sha256": cycles[1]["cycle_sha256"],
        "selected_action_class": _base.recovery.NIST_ACTION_CLASS,
        "candidate_id": _base.recovery.NIST_CANDIDATE_ID,
        "network_authorization_sha256": authorization_sha,
        "network_acquisition_receipt_sha256": receipt["receipt_sha256"],
        "scientific_intake_sha256": intake["report_sha256_without_self_field"],
        "output_blocker": "geometry_condition_mapping_not_established",
        "output_next_action_class": "reviewed_geometry_condition_mapping_assessment",
        "scientific_status_changed": False,
    }
    _rehash(cycle3, "cycle_sha256")
    cycles.append(cycle3)
    stop = {
        "status": "stopped",
        "reason_code": "maximum_cycles_reached",
        "requested_action_class": "reviewed_geometry_condition_mapping_assessment",
        "scientific_status_changed": False,
    }
    manifest["cycles"] = cycles
    manifest["stop"] = stop
    manifest["response_compatible_geometry_evidence_acquired"] = True
    manifest["nist_mds2_2923_acquisition_receipt_sha256"] = receipt["receipt_sha256"]
    manifest["nist_mds2_2923_scientific_intake_sha256"] = intake[
        "report_sha256_without_self_field"
    ]
    manifest["nist_mds2_2923_metadata_sha256"] = EXPECTED_METADATA_SHA256
    _rehash(manifest, "manifest_sha256")
    _write(manifest_path, manifest)
    _write(output / "bounded-stop.json", stop)


def test_successful_nist_chain_rejects_rehashed_receipt_authorization_substitution(
    tmp_path: Path,
) -> None:
    output = _prepare_hardened(tmp_path)
    _build_successful_nist_semantic_fixture(output)
    semantic_hardening.verify_persisted_semantic_boundaries(output)

    receipt_path = output / "nist-network-acquisition-receipt.json"
    receipt = _read(receipt_path)
    receipt["authorization_sha256"] = "0" * 64
    _rehash(receipt, "receipt_sha256")
    _write(receipt_path, receipt)

    rediagnosis_path = output / "nist-post-acquisition-rediagnosis.json"
    rediagnosis = _read(rediagnosis_path)
    rediagnosis["input_acquisition_receipt_sha256"] = receipt["receipt_sha256"]
    _rehash(rediagnosis, "rediagnosis_sha256")
    _write(rediagnosis_path, rediagnosis)

    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    cycle3 = dict(manifest["cycles"][2])
    cycle3["network_acquisition_receipt_sha256"] = receipt["receipt_sha256"]
    _rehash(cycle3, "cycle_sha256")
    manifest["cycles"][2] = cycle3
    manifest["nist_mds2_2923_acquisition_receipt_sha256"] = receipt["receipt_sha256"]
    _rehash(manifest, "manifest_sha256")
    _write(manifest_path, manifest)

    with pytest.raises(
        semantic_hardening.AutonomousProductionSemanticHardeningError,
        match="NIST successful acquisition receipt provenance drifted",
    ):
        semantic_hardening.verify_persisted_semantic_boundaries(output)
