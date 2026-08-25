from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import autonomous_production_live_verifier as live_verifier
from materials_data_analyzer.research_loop import autonomous_production_semantic_hardening as semantic_hardening

_BASE_PATH = Path(__file__).with_name("autonomous_production_transport_recovery_regression_base.py")
_SPEC = importlib.util.spec_from_file_location(
    "_autonomous_production_transport_recovery_regression_base",
    _BASE_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
_base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_base)

_EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
_EXPECTED_ARCHIVE_SHA = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
_EXPECTED_WORKBOOK_SHA = "c889e4e6cd1b86d6efb603f53ce9eda64137f6898b3e6f2b490c70a0db73140c"
_EXPECTED_INCOMPLETE_ROWS = [
    {
        "sheet_name": "AM-AB-H",
        "block_index": 1,
        "excel_row_number": 79,
        "missing_reviewed_numeric_fields": ["load_n"],
        "non_numeric_reviewed_fields": [],
        "raw_anomalous_cell_text": {"load_n": ""},
    }
]
_original_prepare = _base._prepare_pretransport_state


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rehash(value: dict[str, Any], field: str) -> None:
    value.pop(field, None)
    value[field] = _base.recovery._canonical_sha(value)


def _quality_contract_fixture(root: Path) -> Path:
    contract = {
        "schema_version": "1.0",
        "source_id": _EXPECTED_SOURCE_ID,
        "source_archive_sha256": _EXPECTED_ARCHIVE_SHA,
        "workbook_sha256": _EXPECTED_WORKBOOK_SHA,
        "reviewed_intake_schema_version": "2.0",
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
        "interpretation": {
            "missing_value_imputation_authorized": False,
            "inverse_reconstruction_from_tensile_stress_authorized": False,
            "row_exclusion_authorized": False,
            "statistical_independence_established": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
        },
    }
    path = root / "configs/research/in625_tensile_observed_quality.v1.json"
    _write_json(path, contract)
    return path.resolve(strict=True)


def _contract_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _prepare_pretransport_state(
    root: Path,
    output_root: str | Path,
    *,
    persist_partial_nist_bytes: bool = True,
) -> Path:
    output = _original_prepare(
        root,
        output_root,
        persist_partial_nist_bytes=persist_partial_nist_bytes,
    )
    contract_path = _quality_contract_fixture(root)

    quality_path = output / "tensile-quality-verification.json"
    quality = _read(quality_path)
    quality.update(
        {
            "quality_contract": _contract_record(contract_path),
            "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
            "isolated_source_missingness_observed": True,
            "missingness_mechanism_established": False,
        }
    )
    _rehash(quality, "verification_sha256")
    _base._write_json(quality_path, quality)

    rediagnosis_path = output / "quality-aware-rediagnosis.json"
    rediagnosis = _read(rediagnosis_path)
    rediagnosis["observed_quality_verification_sha256"] = quality["verification_sha256"]
    rediagnosis["observed_quality_verification"] = quality
    rediagnosis["evidence_state"] = {
        "real_external_source_acquired": True,
        "real_row_level_measurements_observed": True,
        "measurement_semantics_partially_reviewed": True,
        "replicate_independence_established": False,
        "direct_nist_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "observed_source_quality_contract_verified": True,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "isolated_source_missingness_observed": True,
        "missingness_mechanism_established": False,
        "missing_value_imputation_authorized": False,
    }
    next_action = dict(rediagnosis["next_action"])
    next_action["source_quality_constraint"] = {
        "quality_contract_verified": True,
        "affected_field": "load_n",
        "affected_row_count": 1,
        "missing_value_imputation_authorized": False,
        "inverse_reconstruction_authorized": False,
        "row_exclusion_authorized": False,
    }
    rediagnosis["next_action"] = next_action
    _rehash(rediagnosis, "rediagnosis_sha256")
    _base._write_json(rediagnosis_path, rediagnosis)

    assessment_path = output / "physical-comparability-assessment.json"
    assessment = _read(assessment_path)
    assessment["predecessor_rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    assessment["observed_quality_verification_sha256"] = quality["verification_sha256"]
    assessment["source_quality_constraint"] = {
        "known_incomplete_row_count": 1,
        "known_incomplete_rows": _EXPECTED_INCOMPLETE_ROWS,
        "missing_value_imputation_authorized": False,
        "inverse_reconstruction_authorized": False,
        "row_exclusion_authorized": False,
        "missingness_mechanism_established": False,
    }
    _rehash(assessment, "assessment_sha256")
    _base._write_json(assessment_path, assessment)

    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    cycle1, cycle2 = [dict(item) for item in manifest["cycles"]]
    cycle1["quality_verification_sha256"] = quality["verification_sha256"]
    cycle1["rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    _rehash(cycle1, "cycle_sha256")
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    _rehash(cycle2, "cycle_sha256")
    manifest["cycles"] = [cycle1, cycle2]
    manifest["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    manifest["known_incomplete_rows"] = _EXPECTED_INCOMPLETE_ROWS
    _rehash(manifest, "manifest_sha256")
    _base._write_json(manifest_path, manifest)

    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read(qualification_path)
    qualification["issue_76_automatic_promotion_authorized"] = False
    qualification["paper_and_other_source_lanes_remain_allowed"] = True
    _rehash(qualification, "qualification_sha256")
    _base._write_json(qualification_path, qualification)
    return output


_base._prepare_pretransport_state = _prepare_pretransport_state

for _name in dir(_base):
    if _name.startswith("test_"):
        globals()[_name] = getattr(_base, _name)


def _rehash_predecessor_chain(
    output: Path,
    *,
    mutate_quality: Any | None = None,
    mutate_rediagnosis: Any | None = None,
    mutate_assessment: Any | None = None,
) -> None:
    quality = _read(output / "tensile-quality-verification.json")
    rediagnosis = _read(output / "quality-aware-rediagnosis.json")
    assessment = _read(output / "physical-comparability-assessment.json")
    manifest = _read(output / "autonomous-production-manifest.json")

    quality.pop("verification_sha256", None)
    if mutate_quality is not None:
        mutate_quality(quality)
    quality["verification_sha256"] = _base.recovery._canonical_sha(quality)

    rediagnosis.pop("rediagnosis_sha256", None)
    rediagnosis["observed_quality_verification_sha256"] = quality["verification_sha256"]
    rediagnosis["observed_quality_verification"] = quality
    if mutate_rediagnosis is not None:
        mutate_rediagnosis(rediagnosis)
    rediagnosis["rediagnosis_sha256"] = _base.recovery._canonical_sha(rediagnosis)

    assessment.pop("assessment_sha256", None)
    assessment["predecessor_rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    assessment["observed_quality_verification_sha256"] = quality["verification_sha256"]
    if mutate_assessment is not None:
        mutate_assessment(assessment)
    assessment["assessment_sha256"] = _base.recovery._canonical_sha(assessment)

    cycles = [dict(item) for item in manifest["cycles"]]
    cycle1 = cycles[0]
    cycle1.pop("cycle_sha256", None)
    cycle1["quality_verification_sha256"] = quality["verification_sha256"]
    cycle1["rediagnosis_sha256"] = rediagnosis["rediagnosis_sha256"]
    cycle1["cycle_sha256"] = _base.recovery._canonical_sha(cycle1)

    cycle2 = cycles[1]
    cycle2.pop("cycle_sha256", None)
    cycle2["predecessor_cycle_sha256"] = cycle1["cycle_sha256"]
    cycle2["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    cycle2["cycle_sha256"] = _base.recovery._canonical_sha(cycle2)

    rebuilt = [cycle1, cycle2]
    if len(cycles) == 3:
        cycle3 = cycles[2]
        cycle3.pop("cycle_sha256", None)
        cycle3["predecessor_cycle_sha256"] = cycle2["cycle_sha256"]
        cycle3["cycle_sha256"] = _base.recovery._canonical_sha(cycle3)
        rebuilt.append(cycle3)

    manifest.pop("manifest_sha256", None)
    manifest["cycles"] = rebuilt
    manifest["comparability_assessment_sha256"] = assessment["assessment_sha256"]
    manifest["manifest_sha256"] = _base.recovery._canonical_sha(manifest)

    _base._write_json(output / "tensile-quality-verification.json", quality)
    _base._write_json(output / "quality-aware-rediagnosis.json", rediagnosis)
    _base._write_json(output / "physical-comparability-assessment.json", assessment)
    _base._write_json(output / "autonomous-production-manifest.json", manifest)


def _set_nontransport_stop(output: Path) -> None:
    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    stop = {
        "status": "stopped",
        "reason_code": "registered_capability_unavailable_for_current_next_action",
        "requested_action_class": "full-success-predecessor-fixture",
        "scientific_status_changed": False,
    }
    manifest["stop"] = stop
    _rehash(manifest, "manifest_sha256")
    _base._write_json(manifest_path, manifest)
    _base._write_json(output / "bounded-stop.json", stop)


def test_rehashed_rediagnosis_cannot_promote_model_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    assert live_verifier.verify_live_autonomous_output(output) == "typed_nist_transport_stop_verified"

    def promote(value: dict[str, Any]) -> None:
        value["evidence_state"]["empirical_model_validation_established"] = True

    _rehash_predecessor_chain(output, mutate_rediagnosis=promote)
    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="rediagnosis evidence_state improperly promoted scientific authority",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_rehashed_comparability_cannot_authorize_data_alteration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)

    def widen(value: dict[str, Any]) -> None:
        constraint = value["source_quality_constraint"]
        constraint["missing_value_imputation_authorized"] = True
        constraint["inverse_reconstruction_authorized"] = True
        constraint["row_exclusion_authorized"] = True

    _rehash_predecessor_chain(output, mutate_assessment=widen)
    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="physical comparability source-quality constraint drifted",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_rehashed_qualification_cannot_promote_issue_76_or_close_other_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read(qualification_path)
    qualification["issue_76_automatic_promotion_authorized"] = True
    qualification["paper_and_other_source_lanes_remain_allowed"] = False
    _rehash(qualification, "qualification_sha256")
    _base._write_json(qualification_path, qualification)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="Issue #76 automatic promotion",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_qualification_self_hash_tamper_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    qualification_path = output / "nist-network-policy-qualification.json"
    qualification = _read(qualification_path)
    qualification["qualification_sha256"] = "0" * 64
    _base._write_json(qualification_path, qualification)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="qualification self-hash mismatch",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_full_success_semantic_preflight_rechecks_predecessor_science(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    _set_nontransport_stop(output)

    def promote(value: dict[str, Any]) -> None:
        value["evidence_state"]["direct_nist_condition_comparability_established"] = True

    _rehash_predecessor_chain(output, mutate_rediagnosis=promote)
    with pytest.raises(
        semantic_hardening.AutonomousProductionSemanticHardeningError,
        match="rediagnosis evidence_state improperly promoted scientific authority",
    ):
        semantic_hardening.verify_persisted_semantic_boundaries(output)


def test_nested_quality_contract_cannot_authorize_inverse_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    quality = _read(output / "tensile-quality-verification.json")
    contract_path = Path(quality["quality_contract"]["path"])
    contract = _read(contract_path)
    contract["interpretation"]["inverse_reconstruction_from_tensile_stress_authorized"] = True
    _write_json(contract_path, contract)

    def bind_modified_contract(value: dict[str, Any]) -> None:
        value["quality_contract"] = _contract_record(contract_path)

    _rehash_predecessor_chain(output, mutate_quality=bind_modified_contract)
    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="inverse_reconstruction_from_tensile_stress_authorized",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_full_success_embedded_stop_must_equal_standalone_bounded_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    manifest["stop"] = {
        "status": "completed",
        "reason_code": "contradictory-full-success-stop",
    }
    _rehash(manifest, "manifest_sha256")
    _base._write_json(manifest_path, manifest)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="bounded-stop artifact does not match autonomous manifest stop",
    ):
        live_verifier.verify_live_autonomous_output(output)


def test_manifest_incomplete_row_identity_must_match_verified_quality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _base._prepare_pretransport_state(tmp_path, "outputs/run")
    _base._run_transport_stop(monkeypatch, root=tmp_path)
    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read(manifest_path)
    manifest["known_incomplete_rows"] = [
        {
            **_EXPECTED_INCOMPLETE_ROWS[0],
            "excel_row_number": 80,
        }
    ]
    _rehash(manifest, "manifest_sha256")
    _base._write_json(manifest_path, manifest)

    with pytest.raises(
        live_verifier.AutonomousProductionLiveVerificationError,
        match="manifest incomplete-row identity disagrees",
    ):
        live_verifier.verify_live_autonomous_output(output)


@pytest.mark.parametrize(
    "module_name",
    [
        "materials_data_analyzer.research_loop.autonomous_production_live_verifier_base",
        "materials_data_analyzer.research_loop.autonomous_production_live_verifier_impl",
    ],
)
def test_compatibility_verifier_modules_are_not_executable_bypasses(module_name: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", module_name, "unused-output"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "is not an executable verifier" in completed.stderr


@pytest.mark.parametrize("authority", [True, None])
def test_full_success_preflight_requires_explicit_false_paper_row_authority(
    tmp_path: Path,
    authority: object,
) -> None:
    output = tmp_path / "full-success"
    output.mkdir()
    manifest: dict[str, Any] = {
        "stop": {"status": "completed", "reason_code": "completed"},
    }
    if authority is not None:
        manifest["paper_evidence_promoted_to_row_level_authority"] = authority
    _base._write_json(output / "autonomous-production-manifest.json", manifest)
    _base._write_json(
        output / "bounded-stop.json",
        {"status": "completed", "reason_code": "completed"},
    )

    with pytest.raises(
        semantic_hardening.AutonomousProductionSemanticHardeningError,
        match="must explicitly deny paper evidence row-level authority",
    ):
        semantic_hardening.verify_persisted_semantic_boundaries(output)
