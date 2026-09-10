"""Cross-artifact semantic hardening for autonomous-production live verification.

Self-consistent re-hashing is not sufficient scientific authentication. This module verifies
that predecessor artifacts continue to encode the exact fail-closed authority state and that
their scientific/data-quality claims agree across artifact boundaries on every accepted live
outcome, not only on temporary transport stops.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACTION_CLASS,
    ARTIFACT_ALLOWED_HOSTS,
    CANDIDATE_ID as NIST_CANDIDATE_ID,
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    FRONTIER_PATH,
    IDENTIFIER as NIST_IDENTIFIER,
    MAX_ARTIFACT_BYTES,
    MAX_METADATA_BYTES,
    MAX_NETWORK_REQUESTS,
    MAX_TOTAL_ARTIFACT_BYTES,
    METADATA_ALLOWED_HOSTS,
    METADATA_ENDPOINT,
    POLICY_ID as NIST_POLICY_ID,
    PRODUCT_ID as NIST_PRODUCT_ID,
    TIMEOUT_SECONDS,
)

TRANSPORT_STOP_REASON_CODE = "source_transport_temporarily_unavailable"

_EXPECTED_SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
_EXPECTED_ARCHIVE_SHA256 = (
    "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"
)
_EXPECTED_WORKBOOK_SHA256 = (
    "c889e4e6cd1b86d6efb603f53ce9eda64137f6898b3e6f2b490c70a0db73140c"
)
_EXPECTED_QUALITY_CONTRACT_NAME = "in625_tensile_observed_quality.v1.json"
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
_QUALITY_INTERPRETATION_FALSE_FIELDS = (
    "missing_value_imputation_authorized",
    "inverse_reconstruction_from_tensile_stress_authorized",
    "row_exclusion_authorized",
    "statistical_independence_established",
    "direct_nist_condition_comparability_established",
    "empirical_model_validation_established",
    "hypothesis_truth_established",
    "positive_scientific_closeout_established",
)
_EXPECTED_COMPARABILITY_BINDINGS = {
    "nist_planning_readiness": "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
    "nist_process_conditions": "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
    "nist_melt_pool_measurements": "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
    "nist_case_readme": "data/case_studies/nist_ambench_2018_02/README.md",
    "zenodo_reviewed_tensile_contract": "configs/research/in625_tensile_reviewed_intake.v1.json",
    "zenodo_verified_source": "configs/research/in625_zenodo_20503603_verified_source.v1.json",
    "zenodo_observed_quality_contract": "configs/research/in625_tensile_observed_quality.v1.json",
    "in625_physical_source_frontier": FRONTIER_PATH,
}


class AutonomousProductionSemanticHardeningError(ValueError):
    """Raised when authenticated artifacts disagree about scientific authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionSemanticHardeningError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionSemanticHardeningError(
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


def _verify_manifest_cycle_chain(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    _verify_self_hash(manifest, "manifest_sha256", label="autonomous production manifest")
    raw_cycles = manifest.get("cycles")
    _require(isinstance(raw_cycles, list) and raw_cycles, "autonomous manifest cycles are invalid")
    cycles: list[dict[str, Any]] = []
    predecessor_sha: str | None = None
    for expected_index, raw_cycle in enumerate(raw_cycles, start=1):
        _require(isinstance(raw_cycle, dict), f"cycle {expected_index} must be an object")
        cycle = dict(raw_cycle)
        cycle_sha = _verify_self_hash(cycle, "cycle_sha256", label=f"cycle {expected_index}")
        _require(
            cycle.get("cycle_index") == expected_index,
            f"cycle {expected_index} index drifted",
        )
        if predecessor_sha is not None:
            _require(
                cycle.get("predecessor_cycle_sha256") == predecessor_sha,
                f"cycle {expected_index} predecessor binding mismatch",
            )
        predecessor_sha = cycle_sha
        cycles.append(cycle)
    return cycles


def _load_bound_quality_contract(
    *, root: Path, quality: Mapping[str, Any]
) -> tuple[dict[str, Any], Path]:
    record = _mapping(quality.get("quality_contract"), "tensile quality quality_contract")
    _require(
        set(record) == {"path", "sha256", "bytes"},
        "tensile quality contract binding field set drifted",
    )
    raw_path = record.get("path")
    digest = record.get("sha256")
    byte_count = record.get("bytes")
    _require(isinstance(raw_path, str) and raw_path, "tensile quality contract binding path is invalid")
    _require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        "tensile quality contract binding SHA is invalid",
    )
    _require(
        isinstance(byte_count, int) and not isinstance(byte_count, bool) and byte_count > 0,
        "tensile quality contract binding byte count is invalid",
    )
    try:
        contract_path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise AutonomousProductionSemanticHardeningError(
            "tensile quality contract binding path does not resolve"
        ) from exc
    _require(contract_path.is_file(), "tensile quality contract binding is not a file")
    _require(
        contract_path.name == _EXPECTED_QUALITY_CONTRACT_NAME
        and contract_path.parent.name == "research"
        and contract_path.parent.parent.name == "configs",
        "tensile quality contract binding escaped the exact repository contract location",
    )
    repository_root = contract_path.parents[2]
    _require(
        repository_root in root.parents,
        "tensile quality contract binding is outside the autonomous run repository",
    )
    raw = contract_path.read_bytes()
    _require(len(raw) == byte_count, "tensile quality contract byte count mismatch")
    _require(hashlib.sha256(raw).hexdigest() == digest, "tensile quality contract SHA-256 mismatch")
    try:
        contract = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionSemanticHardeningError(
            "tensile quality contract must be valid UTF-8 JSON"
        ) from exc
    _require(isinstance(contract, dict), "tensile quality contract root must be an object")
    _require(
        contract.get("schema_version") == "1.0"
        and contract.get("source_id") == _EXPECTED_SOURCE_ID
        and contract.get("source_archive_sha256") == _EXPECTED_ARCHIVE_SHA256
        and contract.get("workbook_sha256") == _EXPECTED_WORKBOOK_SHA256
        and contract.get("reviewed_intake_schema_version") == "2.0"
        and contract.get("measurement_row_count") == 200289
        and contract.get("complete_numeric_measurement_row_count") == 200288
        and contract.get("incomplete_numeric_measurement_row_count") == 1
        and contract.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS,
        "tensile quality contract observed-evidence identity drifted",
    )
    interpretation = _mapping(contract.get("interpretation"), "tensile quality contract interpretation")
    for key in _QUALITY_INTERPRETATION_FALSE_FIELDS:
        _require(
            interpretation.get(key) is False,
            f"tensile quality contract improperly authorizes scientific/data alteration: {key}",
        )
    return contract, repository_root


def _verify_repository_binding(
    repository_root: Path,
    value: object,
    *,
    expected_path: str,
    label: str,
) -> None:
    binding = _mapping(value, label)
    _require(set(binding) == {"path", "sha256", "bytes"}, f"{label} binding field set drifted")
    _require(binding.get("path") == expected_path, f"{label} path drifted")
    path = (repository_root / expected_path).resolve(strict=True)
    try:
        path.relative_to(repository_root)
    except ValueError as exc:
        raise AutonomousProductionSemanticHardeningError(f"{label} escaped repository root") from exc
    _require(path.is_file(), f"{label} is not a repository file")
    raw = path.read_bytes()
    _require(binding.get("bytes") == len(raw), f"{label} byte count mismatch")
    _require(binding.get("sha256") == hashlib.sha256(raw).hexdigest(), f"{label} SHA-256 mismatch")


def _verify_qualification(root: Path) -> Path:
    qualification = _load(root, "nist-network-policy-qualification.json")
    _verify_self_hash(
        qualification,
        "qualification_sha256",
        label="NIST network policy qualification",
    )
    _require(
        qualification.get("policy_id") == NIST_POLICY_ID
        and qualification.get("action_class") == NIST_ACTION_CLASS
        and qualification.get("candidate_id") == NIST_CANDIDATE_ID
        and qualification.get("product_id") == NIST_PRODUCT_ID
        and qualification.get("identifier") == NIST_IDENTIFIER,
        "NIST qualification source/frontier identity drifted",
    )
    _require(
        qualification.get("metadata_endpoint") == METADATA_ENDPOINT
        and qualification.get("expected_nerdm_metadata_sha256") == EXPECTED_METADATA_SHA256
        and qualification.get("expected_files")
        == {path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()}
        and qualification.get("metadata_allowed_hosts") == list(METADATA_ALLOWED_HOSTS)
        and qualification.get("artifact_allowed_hosts") == list(ARTIFACT_ALLOWED_HOSTS)
        and qualification.get("maximum_network_requests") == MAX_NETWORK_REQUESTS
        and qualification.get("maximum_metadata_bytes") == MAX_METADATA_BYTES
        and qualification.get("maximum_artifact_bytes") == MAX_ARTIFACT_BYTES
        and qualification.get("maximum_total_artifact_bytes") == MAX_TOTAL_ARTIFACT_BYTES
        and qualification.get("timeout_seconds") == TIMEOUT_SECONDS,
        "NIST qualification finite network contract drifted",
    )
    _require(
        qualification.get("issue_76_automatic_promotion_authorized") is False,
        "NIST qualification authorized Issue #76 automatic promotion",
    )
    _require(
        qualification.get("paper_and_other_source_lanes_remain_allowed") is True,
        "NIST qualification closed independent paper/other-source evidence lanes",
    )
    _require(
        qualification.get("network_access_performed") is False
        and qualification.get("unrestricted_search_authorized") is False
        and qualification.get("arbitrary_url_fetch_authorized") is False
        and qualification.get("scientific_status_changed") is False,
        "NIST qualification widened network or scientific authority",
    )
    raw_frontier_path = qualification.get("frontier_path")
    _require(isinstance(raw_frontier_path, str) and raw_frontier_path, "NIST qualification frontier path is invalid")
    try:
        frontier_path = Path(raw_frontier_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise AutonomousProductionSemanticHardeningError("NIST qualification frontier path does not resolve") from exc
    suffix = Path(FRONTIER_PATH).parts
    _require(
        len(frontier_path.parts) >= len(suffix)
        and tuple(frontier_path.parts[-len(suffix):]) == suffix,
        "NIST qualification frontier path drifted",
    )
    repository_root = frontier_path.parents[len(suffix) - 1]
    _require(repository_root in root.parents, "NIST qualification frontier escaped autonomous run repository")
    _require(
        qualification.get("frontier_sha256") == _sha256_file(frontier_path),
        "NIST qualification frontier SHA-256 mismatch",
    )
    return repository_root


def _verify_secondary_quality_blocker(rediagnosis: Mapping[str, Any]) -> None:
    blockers = rediagnosis.get("secondary_blockers")
    _require(isinstance(blockers, list) and len(blockers) == 1, "rediagnosis secondary blocker set drifted")
    blocker = _mapping(blockers[0], "quality-aware rediagnosis secondary blocker")
    _require(
        blocker.get("code") == "reviewed_numeric_source_missingness_observed"
        and blocker.get("kind") == "data_quality"
        and blocker.get("severity") == "bounded"
        and blocker.get("measurement_row_count") == 200289
        and blocker.get("affected_row_count") == 1
        and blocker.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS
        and blocker.get("blocks_external_evidence_availability") is False
        and blocker.get("blocks_unqualified_use_of_affected_load_value") is True
        and blocker.get("missingness_mechanism_established") is False
        and blocker.get("imputation_authorized") is False
        and blocker.get("row_exclusion_authorized") is False
        and blocker.get("scientific_status_changed") is False,
        "rediagnosis secondary data-quality authority drifted",
    )


def _verify_comparability_bindings(
    assessment: Mapping[str, Any], *, repository_root: Path
) -> None:
    bindings = _mapping(assessment.get("evidence_bindings"), "physical comparability evidence_bindings")
    _require(set(bindings) == set(_EXPECTED_COMPARABILITY_BINDINGS), "physical comparability evidence binding set drifted")
    for key, path in _EXPECTED_COMPARABILITY_BINDINGS.items():
        _verify_repository_binding(
            repository_root,
            bindings.get(key),
            expected_path=path,
            label=f"physical comparability evidence binding {key}",
        )


def _verify_pretransport_science(root: Path, *, manifest: Mapping[str, Any]) -> Path:
    quality = _load(root, "tensile-quality-verification.json")
    rediagnosis = _load(root, "quality-aware-rediagnosis.json")
    assessment = _load(root, "physical-comparability-assessment.json")

    quality_sha = _verify_self_hash(quality, "verification_sha256", label="tensile quality verification")
    rediagnosis_sha = _verify_self_hash(rediagnosis, "rediagnosis_sha256", label="quality-aware rediagnosis")
    _verify_self_hash(assessment, "assessment_sha256", label="physical comparability assessment")

    _require(
        quality.get("measurement_row_count") == 200289
        and quality.get("complete_numeric_measurement_row_count") == 200288
        and quality.get("incomplete_numeric_measurement_row_count") == 1,
        "tensile quality row-count identity drifted",
    )
    _require(quality.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS, "tensile quality incomplete-row identity drifted")
    _require(
        manifest.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS
        and manifest.get("known_incomplete_rows") == quality.get("known_incomplete_rows"),
        "autonomous manifest incomplete-row identity disagrees with verified quality evidence",
    )
    _, repository_root = _load_bound_quality_contract(root=root, quality=quality)
    _require(
        quality.get("isolated_source_missingness_observed") is True
        and quality.get("missingness_mechanism_established") is False
        and quality.get("missing_value_imputation_authorized") is False
        and quality.get("row_exclusion_authorized") is False
        and quality.get("direct_nist_condition_comparability_established") is False
        and quality.get("empirical_model_validation_established") is False
        and quality.get("hypothesis_truth_established") is False
        and quality.get("positive_scientific_closeout_established") is False
        and quality.get("scientific_status_changed") is False,
        "quality evidence scientific state drifted: tensile quality authority",
    )

    _require(rediagnosis.get("observed_quality_verification_sha256") == quality_sha, "rediagnosis/quality digest binding mismatch")
    _require(rediagnosis.get("observed_quality_verification") == quality, "rediagnosis embedded quality evidence disagrees with persisted verification")
    evidence_state = _mapping(rediagnosis.get("evidence_state"), "quality-aware rediagnosis evidence_state")
    _require(
        evidence_state.get("real_external_source_acquired") is True
        and evidence_state.get("real_row_level_measurements_observed") is True
        and evidence_state.get("observed_source_quality_contract_verified") is True
        and evidence_state.get("complete_numeric_measurement_row_count") == 200288
        and evidence_state.get("incomplete_numeric_measurement_row_count") == 1
        and evidence_state.get("isolated_source_missingness_observed") is True,
        "rediagnosis evidence_state lost verified observed evidence",
    )
    for key in (
        "replicate_independence_established",
        "direct_nist_condition_comparability_established",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "missingness_mechanism_established",
        "missing_value_imputation_authorized",
    ):
        _require(evidence_state.get(key) is False, f"rediagnosis evidence_state improperly promoted scientific authority: {key}")
    _verify_secondary_quality_blocker(rediagnosis)

    next_action = _mapping(rediagnosis.get("next_action"), "quality-aware rediagnosis next_action")
    rediagnosis_quality = _mapping(next_action.get("source_quality_constraint"), "quality-aware rediagnosis next_action.source_quality_constraint")
    _require(
        rediagnosis_quality.get("quality_contract_verified") is True
        and rediagnosis_quality.get("affected_field") == "load_n"
        and rediagnosis_quality.get("affected_row_count") == 1
        and rediagnosis_quality.get("missing_value_imputation_authorized") is False
        and rediagnosis_quality.get("inverse_reconstruction_authorized") is False
        and rediagnosis_quality.get("row_exclusion_authorized") is False,
        "rediagnosis source-quality constraint drifted",
    )

    _require(assessment.get("predecessor_rediagnosis_sha256") == rediagnosis_sha, "comparability/rediagnosis digest binding mismatch")
    _require(assessment.get("observed_quality_verification_sha256") == quality_sha, "comparability/quality digest binding mismatch")
    _verify_comparability_bindings(assessment, repository_root=repository_root)
    source_quality = _mapping(assessment.get("source_quality_constraint"), "physical comparability source_quality_constraint")
    _require(
        source_quality.get("known_incomplete_row_count") == 1
        and source_quality.get("known_incomplete_rows") == _EXPECTED_INCOMPLETE_ROWS
        and source_quality.get("known_incomplete_rows") == quality.get("known_incomplete_rows")
        and source_quality.get("missing_value_imputation_authorized") is False
        and source_quality.get("inverse_reconstruction_authorized") is False
        and source_quality.get("row_exclusion_authorized") is False
        and source_quality.get("missingness_mechanism_established") is False,
        "physical comparability source-quality constraint drifted",
    )
    return repository_root


def _verify_successful_nist_chain(root: Path, *, manifest: Mapping[str, Any], cycles: list[dict[str, Any]]) -> None:
    authorization = _load(root, "nist-network-authorization.json")
    receipt = _load(root, "nist-network-acquisition-receipt.json")
    intake = _load(root, "nist-scientific-intake.json")
    rediagnosis = _load(root, "nist-post-acquisition-rediagnosis.json")

    authorization_sha = _verify_self_hash(authorization, "authorization_sha256", label="NIST successful authorization")
    receipt_sha = _verify_self_hash(receipt, "receipt_sha256", label="NIST successful acquisition receipt")
    intake_sha = _verify_self_hash(intake, "report_sha256_without_self_field", label="NIST successful scientific intake")
    rediagnosis_sha = _verify_self_hash(rediagnosis, "rediagnosis_sha256", label="NIST successful post-acquisition rediagnosis")
    _require(bool(rediagnosis_sha), "NIST post-acquisition rediagnosis digest is missing")

    _require(
        authorization.get("authorization_status") == "authorized_exact_nist_mds2_2923_acquisition"
        and authorization.get("policy_id") == NIST_POLICY_ID
        and authorization.get("action_class") == NIST_ACTION_CLASS
        and authorization.get("candidate_id") == NIST_CANDIDATE_ID
        and authorization.get("product_id") == NIST_PRODUCT_ID
        and authorization.get("metadata_endpoint") == METADATA_ENDPOINT
        and authorization.get("expected_nerdm_metadata_sha256") == EXPECTED_METADATA_SHA256
        and authorization.get("expected_files") == {path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()}
        and authorization.get("metadata_allowed_hosts") == list(METADATA_ALLOWED_HOSTS)
        and authorization.get("artifact_allowed_hosts") == list(ARTIFACT_ALLOWED_HOSTS)
        and authorization.get("maximum_network_requests") == MAX_NETWORK_REQUESTS
        and authorization.get("maximum_metadata_bytes") == MAX_METADATA_BYTES
        and authorization.get("maximum_artifact_bytes") == MAX_ARTIFACT_BYTES
        and authorization.get("maximum_total_artifact_bytes") == MAX_TOTAL_ARTIFACT_BYTES
        and authorization.get("timeout_seconds") == TIMEOUT_SECONDS
        and authorization.get("caller_authored_url_used") is False
        and authorization.get("caller_authored_file_queue_used") is False
        and authorization.get("unrestricted_search_authorized") is False
        and authorization.get("arbitrary_url_fetch_authorized") is False
        and authorization.get("network_access_performed") is False
        and authorization.get("scientific_status_changed") is False,
        "NIST successful authorization widened or drifted",
    )
    _require(
        receipt.get("acquisition_status") == "exact_nist_mds2_2923_source_files_acquired"
        and receipt.get("authorization_sha256") == authorization_sha
        and receipt.get("policy_id") == NIST_POLICY_ID
        and receipt.get("action_class") == NIST_ACTION_CLASS
        and receipt.get("candidate_id") == NIST_CANDIDATE_ID
        and receipt.get("product_id") == NIST_PRODUCT_ID
        and receipt.get("metadata_sha256") == EXPECTED_METADATA_SHA256
        and receipt.get("network_requests_performed") == MAX_NETWORK_REQUESTS
        and receipt.get("network_request_budget") == MAX_NETWORK_REQUESTS
        and receipt.get("caller_authored_url_used") is False
        and receipt.get("caller_authored_file_queue_used") is False
        and receipt.get("unrestricted_network_search_performed") is False
        and receipt.get("arbitrary_url_fetch_performed") is False
        and receipt.get("all_acquisition_provenance_authenticated") is True
        and receipt.get("requires_scientific_intake") is True
        and receipt.get("scientific_status_changed") is False,
        "NIST successful acquisition receipt provenance drifted",
    )
    _require(
        rediagnosis.get("input_acquisition_receipt_sha256") == receipt_sha
        and rediagnosis.get("input_scientific_intake_sha256") == intake_sha,
        "NIST successful rediagnosis predecessor digest binding mismatch",
    )
    blocker = _mapping(rediagnosis.get("current_blocker"), "NIST post-acquisition blocker")
    next_action = _mapping(rediagnosis.get("next_action"), "NIST post-acquisition next action")
    boundary = _mapping(rediagnosis.get("scientific_boundary"), "NIST post-acquisition scientific boundary")
    _require(
        blocker.get("code") == "geometry_condition_mapping_not_established"
        and next_action.get("action_class") == "reviewed_geometry_condition_mapping_assessment"
        and boundary.get("response_compatible_geometry_evidence_acquired") is True
        and boundary.get("direct_target_condition_comparability_established") is False
        and boundary.get("cross_machine_pooling_performed") is False
        and boundary.get("calibration_conversion_performed") is False
        and boundary.get("issue_76_eligible") is False
        and boundary.get("issue_76_exact_target_cells_satisfied") == 0
        and boundary.get("empirical_model_validation_established") is False
        and boundary.get("hypothesis_truth_established") is False
        and boundary.get("positive_scientific_closeout_established") is False
        and boundary.get("global_evidence_unavailability_claimed") is False
        and boundary.get("scientific_status_changed") is False,
        "NIST successful rediagnosis scientific authority drifted",
    )
    _require(len(cycles) >= 3, "NIST successful output omitted cycle 3")
    cycle3 = cycles[2]
    _require(
        cycle3.get("selected_action_class") == NIST_ACTION_CLASS
        and cycle3.get("candidate_id") == NIST_CANDIDATE_ID
        and cycle3.get("network_authorization_sha256") == authorization_sha
        and cycle3.get("network_acquisition_receipt_sha256") == receipt_sha
        and cycle3.get("scientific_intake_sha256") == intake_sha
        and cycle3.get("output_blocker") == blocker.get("code")
        and cycle3.get("output_next_action_class") == next_action.get("action_class"),
        "NIST successful cycle-3 provenance binding mismatch",
    )
    _require(
        manifest.get("nist_mds2_2923_acquisition_receipt_sha256") == receipt_sha
        and manifest.get("nist_mds2_2923_scientific_intake_sha256") == intake_sha
        and manifest.get("nist_mds2_2923_metadata_sha256") == EXPECTED_METADATA_SHA256,
        "NIST successful manifest provenance binding mismatch",
    )


def verify_persisted_semantic_boundaries(output_root: str | Path) -> None:
    """Reject self-consistent artifacts that widen persisted scientific authority."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")
    cycles = _verify_manifest_cycle_chain(manifest)
    bounded_stop = _load(root, "bounded-stop.json")

    _require(
        manifest.get("paper_evidence_promoted_to_row_level_authority") is False,
        "autonomous manifest must explicitly deny paper evidence row-level authority",
    )
    stop = _mapping(manifest.get("stop"), "autonomous production manifest stop")
    _require(dict(stop) == bounded_stop, "bounded-stop artifact does not match autonomous manifest stop")

    qualification_repository_root = _verify_qualification(root)
    predecessor_repository_root = _verify_pretransport_science(root, manifest=manifest)
    _require(
        qualification_repository_root == predecessor_repository_root,
        "NIST qualification and predecessor science resolve to different repository roots",
    )

    if manifest.get("response_compatible_geometry_evidence_acquired") is True:
        _verify_successful_nist_chain(root, manifest=manifest, cycles=cycles)


__all__ = [
    "AutonomousProductionSemanticHardeningError",
    "TRANSPORT_STOP_REASON_CODE",
    "verify_persisted_semantic_boundaries",
]
