"""Final merge-gate hardening for persisted autonomous-production evidence.

This layer deliberately re-opens the persisted artifacts after the existing semantic verifier.
It binds repository evidence to the actual checkout root and closes full-success provenance
surfaces that must not be bypassable by a self-consistently re-hashed manifest.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACTION_CLASS,
    CANDIDATE_ID as NIST_CANDIDATE_ID,
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    FRONTIER_PATH,
    PRODUCT_ID as NIST_PRODUCT_ID,
)
from .public_data_acquisition import AUTO

TRANSPORT_STOP_REASON_CODE = "source_transport_temporarily_unavailable"
_EXPECTED_ZENODO_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
_EXPECTED_ZENODO_ARCHIVE_SHA256 = (
    "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
)
_EXPECTED_QUALITY_CONTRACT = "configs/research/in625_tensile_observed_quality.v1.json"
_EXPECTED_BINDINGS = {
    "nist_planning_readiness": "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
    "nist_process_conditions": "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
    "nist_melt_pool_measurements": "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
    "nist_case_readme": "data/case_studies/nist_ambench_2018_02/README.md",
    "zenodo_reviewed_tensile_contract": "configs/research/in625_tensile_reviewed_intake.v1.json",
    "zenodo_verified_source": "configs/research/in625_zenodo_20503603_verified_source.v1.json",
    "zenodo_observed_quality_contract": _EXPECTED_QUALITY_CONTRACT,
    "in625_physical_source_frontier": FRONTIER_PATH,
}


class AutonomousProductionMergeGateHardeningError(ValueError):
    """Raised when the final persisted merge-gate contract is not exact."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionMergeGateHardeningError(message)


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionMergeGateHardeningError(
            f"{name} must be valid persisted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{name} root must be an object")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    return value


def _verify_self_hash(value: Mapping[str, Any], field: str, *, label: str) -> str:
    digest = value.get(field)
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        f"{label} {field} is missing or non-canonical",
    )
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{label} self-hash mismatch")
    return digest


def _trusted_repository_root() -> Path:
    """Return the checkout root containing this verifier, never an output-derived ancestor."""
    root = Path(__file__).resolve().parents[3]
    required = root / _EXPECTED_QUALITY_CONTRACT
    _require(required.is_file(), "trusted checkout root does not contain the pinned quality contract")
    _require((root / FRONTIER_PATH).is_file(), "trusted checkout root does not contain the pinned frontier")
    return root


def _inside(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionMergeGateHardeningError(
            f"{label} escaped the trusted root"
        ) from exc


def _verify_bound_file(
    *, repository_root: Path, binding: object, expected_path: str, label: str
) -> None:
    record = _mapping(binding, label)
    _require(set(record) == {"path", "sha256", "bytes"}, f"{label} field set drifted")
    _require(record.get("path") == expected_path, f"{label} path drifted")
    path = (repository_root / expected_path).resolve(strict=True)
    _inside(path, repository_root, label=label)
    raw = path.read_bytes()
    _require(record.get("bytes") == len(raw), f"{label} byte count mismatch")
    _require(
        record.get("sha256") == hashlib.sha256(raw).hexdigest(),
        f"{label} SHA-256 mismatch",
    )


def _verify_cycle1_network_receipt(root: Path, cycle1: Mapping[str, Any]) -> None:
    receipt = _load(root, "network-acquisition-receipt.json")
    receipt_sha = _verify_self_hash(
        receipt, "receipt_sha256", label="cycle-1 network acquisition receipt"
    )
    _require(
        cycle1.get("network_receipt_sha256") == receipt_sha,
        "cycle 1 network receipt binding mismatch",
    )
    _require(
        receipt.get("source_id") == _EXPECTED_ZENODO_SOURCE_ID
        and receipt.get("zenodo_record_id") == 20503603
        and receipt.get("archive_sha256") == _EXPECTED_ZENODO_ARCHIVE_SHA256,
        "cycle-1 Zenodo source identity drifted",
    )
    _require(
        receipt.get("network_access_performed") is True
        and receipt.get("download_executed") is True
        and receipt.get("archive_checksum_verified") is True
        and receipt.get("archive_size_verified") is True
        and receipt.get("exact_host_authority_preserved") is True,
        "cycle-1 acquisition provenance was not fully authenticated",
    )
    boundary = _mapping(receipt.get("scientific_boundary"), "cycle-1 acquisition scientific boundary")
    _require(
        boundary.get("automatic_scientific_promotion") is False
        and boundary.get("direct_nist_comparability_established") is False
        and boundary.get("empirical_model_validation_established") is False
        and boundary.get("hypothesis_truth_established") is False
        and boundary.get("positive_scientific_closeout_established") is False,
        "cycle-1 acquisition receipt widened scientific authority",
    )


def _verify_checkout_bindings(root: Path, cycles: list[dict[str, Any]]) -> Path:
    repository_root = _trusted_repository_root().resolve(strict=True)
    _inside(root, repository_root, label="autonomous production output")

    quality = _load(root, "tensile-quality-verification.json")
    quality_binding = _mapping(quality.get("quality_contract"), "tensile quality quality_contract")
    raw_quality_path = quality_binding.get("path")
    _require(isinstance(raw_quality_path, str) and raw_quality_path, "quality contract path is invalid")
    quality_path = Path(raw_quality_path).expanduser().resolve(strict=True)
    expected_quality_path = (repository_root / _EXPECTED_QUALITY_CONTRACT).resolve(strict=True)
    _require(quality_path == expected_quality_path, "quality contract is not bound to the trusted checkout")
    raw_quality = quality_path.read_bytes()
    _require(quality_binding.get("bytes") == len(raw_quality), "quality contract byte count mismatch")
    _require(
        quality_binding.get("sha256") == hashlib.sha256(raw_quality).hexdigest(),
        "quality contract SHA-256 mismatch against trusted checkout",
    )

    qualification = _load(root, "nist-network-policy-qualification.json")
    raw_frontier = qualification.get("frontier_path")
    _require(isinstance(raw_frontier, str) and raw_frontier, "NIST qualification frontier path is invalid")
    frontier = Path(raw_frontier).expanduser().resolve(strict=True)
    expected_frontier = (repository_root / FRONTIER_PATH).resolve(strict=True)
    _require(frontier == expected_frontier, "NIST qualification frontier is not bound to trusted checkout")
    _require(
        qualification.get("frontier_sha256") == hashlib.sha256(frontier.read_bytes()).hexdigest(),
        "NIST qualification frontier SHA-256 mismatch against trusted checkout",
    )

    assessment = _load(root, "physical-comparability-assessment.json")
    bindings = _mapping(assessment.get("evidence_bindings"), "physical comparability evidence bindings")
    _require(set(bindings) == set(_EXPECTED_BINDINGS), "physical comparability binding set drifted")
    for key, relative in _EXPECTED_BINDINGS.items():
        _verify_bound_file(
            repository_root=repository_root,
            binding=bindings.get(key),
            expected_path=relative,
            label=f"physical comparability binding {key}",
        )

    _require(cycles, "autonomous production cycle chain is empty")
    _verify_cycle1_network_receipt(root, cycles[0])
    return repository_root


def _verify_package_receipt(
    *,
    root: Path,
    path: str,
    rule: Mapping[str, Any],
    package_index: int,
    top_receipt: Mapping[str, Any],
) -> None:
    nist_root = (root / "nist-mds2-2923").resolve(strict=True)
    package = (nist_root / f"artifact-{package_index:02d}").resolve(strict=True)
    expected_artifact = (package / path).resolve(strict=True)
    _inside(package, nist_root, label=f"NIST package {package_index}")
    _inside(expected_artifact, package, label=f"NIST artifact {path}")
    _require(expected_artifact.is_file(), f"NIST persisted artifact missing: {path}")
    raw = expected_artifact.read_bytes()
    _require(len(raw) == rule["size_bytes"], f"NIST persisted artifact size drifted: {path}")
    _require(hashlib.sha256(raw).hexdigest() == rule["sha256"], f"NIST persisted artifact SHA drifted: {path}")

    _require(
        Path(str(top_receipt.get("package_directory"))).resolve(strict=True) == package,
        f"NIST receipt package directory drifted: {path}",
    )
    _require(
        top_receipt.get("candidate_id") == f"nist-pdr:{NIST_PRODUCT_ID}:{path}"
        and top_receipt.get("decision") == AUTO
        and top_receipt.get("executed") is True
        and top_receipt.get("artifact_path") == path
        and top_receipt.get("artifact_sha256") == rule["sha256"]
        and top_receipt.get("artifact_size_bytes") == rule["size_bytes"]
        and top_receipt.get("metadata_sha256") == EXPECTED_METADATA_SHA256
        and top_receipt.get("recorded_acquisition_provenance_authenticated") is True
        and top_receipt.get("scientific_status_changed") is False
        and top_receipt.get("requires_scientific_intake") is True,
        f"NIST per-file acquisition receipt drifted: {path}",
    )

    persisted = _load(package, "acquisition_receipt.json")
    _require(
        persisted == {key: value for key, value in top_receipt.items() if key != "package_directory"},
        f"NIST persisted package receipt disagrees with top-level receipt: {path}",
    )
    manifest_path = package / "acquisition_manifest.json"
    declaration_path = package / "acquisition_declaration.json"
    metadata_path = package / "source_metadata.json"
    _require(manifest_path.is_file() and declaration_path.is_file() and metadata_path.is_file(), f"NIST package provenance files missing: {path}")
    _require(
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == top_receipt.get("acquisition_manifest_sha256"),
        f"NIST acquisition manifest digest drifted: {path}",
    )
    _require(
        hashlib.sha256(declaration_path.read_bytes()).hexdigest()
        == top_receipt.get("acquisition_declaration_sha256"),
        f"NIST acquisition declaration digest drifted: {path}",
    )
    _require(
        hashlib.sha256(metadata_path.read_bytes()).hexdigest() == EXPECTED_METADATA_SHA256,
        f"NIST package source metadata digest drifted: {path}",
    )


def _verify_successful_nist_chain(root: Path, manifest: Mapping[str, Any], cycles: list[dict[str, Any]]) -> None:
    _require(len(cycles) >= 3, "successful NIST outcome requires cycle 3")
    cycle3 = cycles[2]
    _require(
        cycle3.get("selected_action_class") == NIST_ACTION_CLASS
        and cycle3.get("candidate_id") == NIST_CANDIDATE_ID,
        "successful NIST cycle-3 identity drifted",
    )
    _require(
        manifest.get("response_compatible_geometry_evidence_acquired") is True,
        "successful NIST outcome omitted response-compatible geometry evidence",
    )

    receipt = _load(root, "nist-network-acquisition-receipt.json")
    receipt_sha = _verify_self_hash(receipt, "receipt_sha256", label="NIST successful acquisition receipt")
    _require(
        receipt.get("acquisition_status") == "exact_nist_mds2_2923_source_files_acquired"
        and receipt.get("candidate_id") == NIST_CANDIDATE_ID
        and receipt.get("product_id") == NIST_PRODUCT_ID
        and receipt.get("metadata_sha256") == EXPECTED_METADATA_SHA256
        and receipt.get("network_requests_performed") == 3
        and receipt.get("network_request_budget") == 3
        and receipt.get("caller_authored_url_used") is False
        and receipt.get("caller_authored_file_queue_used") is False
        and receipt.get("unrestricted_network_search_performed") is False
        and receipt.get("arbitrary_url_fetch_performed") is False
        and receipt.get("all_acquisition_provenance_authenticated") is True
        and receipt.get("requires_scientific_intake") is True
        and receipt.get("scientific_status_changed") is False,
        "NIST successful acquisition receipt aggregate contract drifted",
    )

    artifact_paths = _mapping(receipt.get("artifact_paths"), "NIST successful artifact_paths")
    _require(set(artifact_paths) == set(EXPECTED_FILES), "NIST successful artifact path set drifted")
    receipts = receipt.get("receipts")
    _require(isinstance(receipts, list) and len(receipts) == len(EXPECTED_FILES), "NIST successful per-file receipt count drifted")
    expected_total = sum(int(rule["size_bytes"]) for rule in EXPECTED_FILES.values())
    _require(receipt.get("artifact_bytes_acquired") == expected_total, "NIST successful acquired byte total drifted")

    nist_root = (root / "nist-mds2-2923").resolve(strict=True)
    for index, (path, rule) in enumerate(EXPECTED_FILES.items(), start=1):
        package = (nist_root / f"artifact-{index:02d}").resolve(strict=True)
        expected_path = (package / path).resolve(strict=True)
        _require(
            Path(str(artifact_paths[path])).resolve(strict=True) == expected_path,
            f"NIST artifact_paths binding drifted: {path}",
        )
        top = receipts[index - 1]
        _require(isinstance(top, Mapping), f"NIST per-file receipt {index} must be an object")
        _verify_package_receipt(
            root=root,
            path=path,
            rule=rule,
            package_index=index,
            top_receipt=top,
        )

    intake = _load(root, "nist-scientific-intake.json")
    intake_sha = _verify_self_hash(
        intake,
        "report_sha256_without_self_field",
        label="NIST scientific intake",
    )
    source = _mapping(intake.get("source"), "NIST intake source")
    inventory = _mapping(intake.get("in625_inventory"), "NIST intake inventory")
    semantics = _mapping(intake.get("measurement_semantics"), "NIST intake measurement semantics")
    issue76 = _mapping(intake.get("issue_76"), "NIST intake Issue #76")
    boundary = _mapping(intake.get("scientific_boundary"), "NIST intake scientific boundary")
    _require(
        source.get("product_id") == NIST_PRODUCT_ID
        and source.get("doi") == "10.18434/mds2-2923"
        and source.get("workbook_sha256") == EXPECTED_FILES["Master_TrackList_Measurements.xlsx"]["sha256"]
        and source.get("readme_sha256") == EXPECTED_FILES["2923_README.txt"]["sha256"]
        and source.get("nerdm_metadata_sha256") == EXPECTED_METADATA_SHA256,
        "NIST intake exact source identity drifted",
    )
    _require(
        inventory.get("measurement_row_count") == 178
        and inventory.get("physical_track_count") == 106
        and inventory.get("machine_measurement_counts") == {"AMMT": 34, "EOS M270": 144}
        and inventory.get("machine_physical_track_counts") == {"AMMT": 34, "EOS M270": 72},
        "NIST intake measurement inventory drifted",
    )
    _require(
        semantics.get("calibration_conversion_performed") is False
        and issue76.get("eligible") is False
        and issue76.get("exact_target_cells_satisfied") == 0,
        "NIST intake calibration or Issue #76 boundary drifted",
    )
    _require(
        boundary.get("adjacent_machine_stratified_descriptive_intake_prepared") is True
        and boundary.get("cross_machine_pooling_eligible") is False
        and boundary.get("predictive_modeling_eligible_from_this_audit") is False
        and boundary.get("causal_inference_eligible_from_this_audit") is False
        and boundary.get("optimization_eligible_from_this_audit") is False
        and boundary.get("human_scientific_review_decision_created") is False
        and boundary.get("scientific_support_established") is False
        and boundary.get("scientific_status_changed") is False,
        "NIST intake scientific authority drifted",
    )

    rediagnosis = _load(root, "nist-post-acquisition-rediagnosis.json")
    rediagnosis_sha = _verify_self_hash(
        rediagnosis, "rediagnosis_sha256", label="NIST post-acquisition rediagnosis"
    )
    next_action = _mapping(rediagnosis.get("next_action"), "NIST post-acquisition next_action")
    red_boundary = _mapping(
        rediagnosis.get("scientific_boundary"), "NIST post-acquisition scientific boundary"
    )
    _require(
        rediagnosis.get("input_acquisition_receipt_sha256") == receipt_sha
        and rediagnosis.get("input_scientific_intake_sha256") == intake_sha
        and _mapping(rediagnosis.get("current_blocker"), "NIST current blocker").get("code")
        == "geometry_condition_mapping_not_established"
        and next_action.get("action_class") == "reviewed_geometry_condition_mapping_assessment"
        and next_action.get("network_access_performed") is False
        and next_action.get("automatic_execution_authorized") is False
        and rediagnosis.get("new_verified_information") is True
        and rediagnosis.get("scientific_status_changed") is False,
        "NIST post-acquisition transition drifted",
    )
    _require(
        red_boundary.get("response_compatible_geometry_evidence_acquired") is True
        and red_boundary.get("direct_target_condition_comparability_established") is False
        and red_boundary.get("cross_machine_pooling_performed") is False
        and red_boundary.get("calibration_conversion_performed") is False
        and red_boundary.get("issue_76_eligible") is False
        and red_boundary.get("issue_76_exact_target_cells_satisfied") == 0
        and red_boundary.get("empirical_model_validation_established") is False
        and red_boundary.get("hypothesis_truth_established") is False
        and red_boundary.get("positive_scientific_closeout_established") is False
        and red_boundary.get("global_evidence_unavailability_claimed") is False
        and red_boundary.get("scientific_status_changed") is False,
        "NIST post-acquisition scientific boundary drifted",
    )

    _require(
        cycle3.get("network_acquisition_receipt_sha256") == receipt_sha
        and cycle3.get("scientific_intake_sha256") == intake_sha
        and cycle3.get("output_blocker") == "geometry_condition_mapping_not_established"
        and cycle3.get("output_next_action_class") == "reviewed_geometry_condition_mapping_assessment"
        and cycle3.get("scientific_status_changed") is False,
        "NIST successful cycle-3 evidence binding drifted",
    )
    _require(
        manifest.get("nist_mds2_2923_acquisition_receipt_sha256") == receipt_sha
        and manifest.get("nist_mds2_2923_scientific_intake_sha256") == intake_sha
        and manifest.get("nist_mds2_2923_metadata_sha256") == EXPECTED_METADATA_SHA256,
        "NIST successful manifest evidence binding drifted",
    )
    _require(isinstance(rediagnosis_sha, str), "NIST rediagnosis self-hash missing")


def verify_final_merge_gate_boundaries(output_root: str | Path) -> None:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")
    cycles_raw = manifest.get("cycles")
    _require(isinstance(cycles_raw, list) and cycles_raw, "autonomous production cycles are invalid")
    cycles: list[dict[str, Any]] = []
    for index, cycle in enumerate(cycles_raw, start=1):
        _require(isinstance(cycle, dict), f"cycle {index} must be an object")
        cycles.append(dict(cycle))

    _verify_checkout_bindings(root, cycles)

    stop = _mapping(manifest.get("stop"), "autonomous production stop")
    if stop.get("reason_code") == TRANSPORT_STOP_REASON_CODE:
        return

    if len(cycles) >= 3 and cycles[2].get("selected_action_class") == NIST_ACTION_CLASS:
        _verify_successful_nist_chain(root, manifest, cycles)


__all__ = [
    "AutonomousProductionMergeGateHardeningError",
    "verify_final_merge_gate_boundaries",
]
