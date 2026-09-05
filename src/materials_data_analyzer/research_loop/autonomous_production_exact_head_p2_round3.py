"""Third exact-head fail-closed closure for PR #233.

This layer addresses the Codex review of exact head
``82bf4a09f3b01f40f2563dfb92f4cfc8ebaa4250``. It adds only stricter
verification: duplicate-key rejection before any provenance parsing,
relocation-safe interpretation of historical checkout-bound paths, exact
late-cycle report authentication, transport partial-output consistency,
aggregate NERDm metadata binding, and canonical tensile quality projection.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_merge_gate_lifecycle as _lifecycle
from . import autonomous_production_semantic_hardening as _semantic

AutonomousProductionExactHeadRound3Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_REAL_PATH = Path
_ORIGINAL_LOAD_BOUND_QUALITY_CONTRACT = _semantic._load_bound_quality_contract
_ORIGINAL_VERIFY_QUALIFICATION = _semantic._verify_qualification
_ORIGINAL_REVIEWED_TENSILE_CHAIN = _lifecycle._verify_reviewed_tensile_chain
_INSTALLED = False

_REVIEWED_TENSILE_POLICY = (
    "configs/research/in625_tensile_reviewed_intake.v1.json"
)
_QUALITY_CONTRACT = "configs/research/in625_tensile_observed_quality.v1.json"
_REVIEWED_TENSILE_MANIFEST = "reviewed-tensile/reviewed_tensile_manifest.v2.json"
_REVIEWED_TENSILE_ROWS = "reviewed-tensile/reviewed_tensile_rows.v2.jsonl"
_SELECTED_SOURCE_ROOT = "selected-source-files"

_LATE_SELF_HASH_SPECS: tuple[tuple[str, str], ...] = (
    ("calibration-protocol-bridge-capability-result.json", "report_sha256_without_self_field"),
    ("calibration-record-source-discovery.json", "report_sha256_without_self_field"),
    ("capability-gap-3.json", "capability_gap_sha256_without_self_field"),
    ("capability-candidate-3.json", "capability_candidate_sha256_without_self_field"),
    ("capability-verification-3.json", "capability_verification_sha256_without_self_field"),
    ("capability-registry-promoted-3.json", "capability_registry_sha256_without_self_field"),
    ("nist-ammt-derived-candidate-authorization.json", "authorization_sha256"),
    ("nist-ammt-calibration-candidate-acquisition.json", "report_sha256_without_self_field"),
    ("nist-ammt-calibration-candidate-bridge-assessment.json", "report_sha256_without_self_field"),
    ("capability-gap-4.json", "capability_gap_sha256_without_self_field"),
    ("capability-specification-4.json", "capability_specification_sha256_without_self_field"),
    ("capability-resolution-4-derived.json", "report_sha256_without_self_field"),
    ("capability-candidate-4.json", "capability_candidate_sha256_without_self_field"),
    ("capability-verification-4.json", "capability_verification_sha256_without_self_field"),
    ("capability-registry-promoted-4.json", "capability_registry_sha256_without_self_field"),
    ("nist-mds2-2923-reference-chain-evidence.json", "report_sha256_without_self_field"),
    ("mds2-2923-experiment-identity-reference-chain.json", "report_sha256_without_self_field"),
    ("capability-gap-5.json", "capability_gap_sha256_without_self_field"),
)

_LATE_BINDINGS: tuple[tuple[str, tuple[tuple[str, int | None, str], ...]], ...] = (
    (
        "calibration-protocol-bridge-capability-result.json",
        (("manifest", None, "bridge_capability_execution_sha256"),),
    ),
    (
        "calibration-record-source-discovery.json",
        (("manifest", None, "nist_ammt_source_discovery_sha256"),),
    ),
    ("capability-gap-3.json", (("cycle", 9, "capability_gap_sha256"),)),
    (
        "capability-candidate-3.json",
        (
            ("cycle", 9, "capability_candidate_sha256"),
            ("cycle", 10, "capability_candidate_sha256"),
        ),
    ),
    (
        "capability-verification-3.json",
        (
            ("manifest", None, "third_capability_verification_sha256"),
            ("cycle", 10, "capability_verification_sha256"),
        ),
    ),
    (
        "capability-registry-promoted-3.json",
        (
            ("manifest", None, "third_promoted_capability_registry_sha256"),
            ("cycle", 10, "promoted_registry_sha256"),
        ),
    ),
    (
        "nist-ammt-calibration-candidate-acquisition.json",
        (("manifest", None, "derived_candidate_acquisition_sha256"),),
    ),
    (
        "nist-ammt-calibration-candidate-bridge-assessment.json",
        (("manifest", None, "calibration_candidate_bridge_assessment_sha256"),),
    ),
    (
        "capability-candidate-4.json",
        (
            ("manifest", None, "fourth_capability_candidate_sha256"),
            ("cycle", 11, "capability_candidate_sha256"),
        ),
    ),
    (
        "capability-verification-4.json",
        (("cycle", 12, "capability_verification_sha256"),),
    ),
    (
        "capability-registry-promoted-4.json",
        (("cycle", 12, "promoted_registry_sha256"),),
    ),
    (
        "nist-mds2-2923-reference-chain-evidence.json",
        (("manifest", None, "naderi_reference_evidence_sha256"),),
    ),
    (
        "mds2-2923-experiment-identity-reference-chain.json",
        (
            ("manifest", None, "reference_chain_assessment_sha256"),
            ("cycle", 12, "reference_graph_sha256"),
        ),
    ),
)

_DENIED_LATE_TRUE_FIELDS = {
    "acquisition_success_establishes_calibration_bridge",
    "automatic_execution_authorized",
    "automatic_scientific_promotion",
    "bridge_established",
    "candidate_urls_gain_acquisition_authority",
    "causal_authority_established",
    "causal_authority_granted",
    "causal_inference_authorized",
    "causal_inference_eligible_from_this_audit",
    "cross_machine_pooling_authorized",
    "direct_nist_condition_comparability_established",
    "direct_numerical_cross_source_validation_authorized",
    "direct_numerical_validation_authorized",
    "direct_target_condition_comparability_established",
    "empirical_model_validation_established",
    "global_evidence_unavailability_claimed",
    "hypothesis_truth_established",
    "literature_promoted_to_row_level_measurement_authority",
    "network_failure_interpreted_as_negative_scientific_evidence",
    "numerical_cross_source_validation_authorized",
    "optimization_authority_established",
    "optimization_authority_granted",
    "optimization_authorized",
    "optimization_eligible_from_this_audit",
    "paper_claims_promoted_to_row_level_authority",
    "paper_evidence_promoted_to_row_level_authority",
    "positive_scientific_closeout",
    "positive_scientific_closeout_established",
    "scientific_status_change_authorized",
    "scientific_status_changed",
    "scientific_support_established",
    "source_acquisition_success_interpreted_as_scientific_support",
}
_ZERO_LATE_AUTHORITY_FIELDS = {
    "directly_comparable_mds2_rows",
    "issue_76_exact_target_cells_satisfied",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound3Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _safe_historical_suffix(
    value: object, *, expected_parts: tuple[str, ...], label: str
) -> str:
    _require(isinstance(value, str) and value, f"{label} is missing")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = tuple(part for part in path.parts if part not in {"/", ""})
    _require(
        all(part not in {".", ".."} for part in parts),
        f"{label} contains traversal components",
    )
    _require(
        len(parts) >= len(expected_parts)
        and parts[-len(expected_parts) :] == expected_parts,
        f"{label} does not end in the exact authenticated suffix",
    )
    return value


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AutonomousProductionExactHeadRound3Error(
                f"persisted provenance JSON contains duplicate key: {key}"
            )
        result[key] = value
    return result


def verify_exact_head_round3_preflight(output_root: str | Path) -> None:
    """Reject ambiguous persisted JSON bytes before any existing verifier parses them."""
    root = Path(output_root).expanduser().resolve(strict=True)
    for path in sorted(root.rglob("*.json")):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise AutonomousProductionExactHeadRound3Error(
                "persisted provenance JSON escaped the replay root"
            ) from exc
        try:
            json.loads(
                resolved.read_text(encoding="utf-8"),
                object_pairs_hook=_duplicate_rejecting_object,
            )
        except AutonomousProductionExactHeadRound3Error:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AutonomousProductionExactHeadRound3Error(
                f"{path.relative_to(root)} must be unambiguous valid UTF-8 JSON"
            ) from exc


def _trusted_repository_root() -> Path:
    return _merge_gate._trusted_repository_root().resolve(strict=True)


def _relocation_safe_quality_contract(
    *, root: Path, quality: Mapping[str, Any]
) -> tuple[dict[str, Any], Path]:
    record = _mapping(
        quality.get("quality_contract"),
        label="tensile quality quality_contract",
    )
    recorded = _safe_historical_suffix(
        record.get("path"),
        expected_parts=tuple(Path(_QUALITY_CONTRACT).parts),
        label="tensile quality historical contract path",
    )
    trusted_root = _trusted_repository_root()
    current = (trusted_root / _QUALITY_CONTRACT).resolve(strict=True)
    original_path_factory = _semantic.Path

    def relocated_path_factory(*values: object) -> Path:
        if len(values) == 1 and isinstance(values[0], str) and values[0] == recorded:
            return current
        return _REAL_PATH(*values)

    _semantic.Path = relocated_path_factory  # type: ignore[assignment]
    try:
        synthetic_root = trusted_root / "outputs" / "_replay-location"
        return _ORIGINAL_LOAD_BOUND_QUALITY_CONTRACT(
            root=synthetic_root,
            quality=quality,
        )
    finally:
        _semantic.Path = original_path_factory


def _relocation_safe_qualification(root: Path) -> Path:
    qualification = _semantic._load(root, "nist-network-policy-qualification.json")
    raw_frontier = _safe_historical_suffix(
        qualification.get("frontier_path"),
        expected_parts=tuple(Path(_semantic.FRONTIER_PATH).parts),
        label="NIST qualification historical frontier path",
    )
    trusted_root = _trusted_repository_root()
    current = (trusted_root / _semantic.FRONTIER_PATH).resolve(strict=True)
    original_path_factory = _semantic.Path
    original_load = _semantic._load

    def relocated_path_factory(*values: object) -> Path:
        if len(values) == 1 and isinstance(values[0], str) and values[0] == raw_frontier:
            return current
        return _REAL_PATH(*values)

    def relocated_load(call_root: Path, name: str) -> dict[str, Any]:
        if name == "nist-network-policy-qualification.json":
            return qualification
        return original_load(call_root, name)

    _semantic.Path = relocated_path_factory  # type: ignore[assignment]
    _semantic._load = relocated_load  # type: ignore[assignment]
    try:
        synthetic_root = trusted_root / "outputs" / "_replay-location"
        return _ORIGINAL_VERIFY_QUALIFICATION(synthetic_root)
    finally:
        _semantic.Path = original_path_factory
        _semantic._load = original_load  # type: ignore[assignment]


def _relocation_safe_reviewed_tensile_chain(
    *,
    root: Path,
    repository_root: Path,
    cycle1: Mapping[str, Any],
    archive_receipt: Mapping[str, Any],
    selected_records: Mapping[str, Mapping[str, Any]],
) -> None:
    manifest = _merge_gate._load(root, _REVIEWED_TENSILE_MANIFEST)
    policy_record = _mapping(manifest.get("policy"), label="reviewed tensile manifest policy")
    workbook_record = _mapping(
        manifest.get("workbook"), label="reviewed tensile manifest workbook"
    )
    documentation_record = _mapping(
        manifest.get("documentation"),
        label="reviewed tensile manifest documentation",
    )
    row_record = _mapping(
        manifest.get("row_artifact"), label="reviewed tensile row artifact"
    )

    policy_path = (repository_root / _REVIEWED_TENSILE_POLICY).resolve(strict=True)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    _require(isinstance(policy, dict), "reviewed tensile policy root must be an object")

    path_mapping: dict[str, Path] = {}
    recorded_policy = _safe_historical_suffix(
        policy_record.get("path"),
        expected_parts=tuple(Path(_REVIEWED_TENSILE_POLICY).parts),
        label="reviewed tensile historical policy path",
    )
    path_mapping[recorded_policy] = policy_path

    for label, manifest_record, policy_key in (
        ("workbook", workbook_record, "workbook"),
        ("documentation", documentation_record, "documentation"),
    ):
        policy_source = _mapping(
            policy.get(policy_key), label=f"reviewed tensile policy {policy_key}"
        )
        member = policy_source.get("archive_member_path")
        _require(isinstance(member, str) and member, f"reviewed tensile {label} member is invalid")
        member_path = PurePosixPath(member)
        _require(
            not member_path.is_absolute()
            and all(part not in {"", ".", ".."} for part in member_path.parts),
            f"reviewed tensile {label} member is unsafe",
        )
        expected_parts = (_SELECTED_SOURCE_ROOT, *member_path.parts)
        recorded = _safe_historical_suffix(
            manifest_record.get("path"),
            expected_parts=expected_parts,
            label=f"reviewed tensile historical {label} path",
        )
        current = (root / _SELECTED_SOURCE_ROOT / Path(*member_path.parts)).resolve(
            strict=True
        )
        path_mapping[recorded] = current

    recorded_rows = _safe_historical_suffix(
        row_record.get("path"),
        expected_parts=tuple(Path(_REVIEWED_TENSILE_ROWS).parts),
        label="reviewed tensile historical row-artifact path",
    )
    path_mapping[recorded_rows] = (root / _REVIEWED_TENSILE_ROWS).resolve(strict=True)

    original_path_factory = _lifecycle.Path

    def relocated_path_factory(*values: object) -> Path:
        if len(values) == 1 and isinstance(values[0], str) and values[0] in path_mapping:
            return path_mapping[values[0]]
        return _REAL_PATH(*values)

    _lifecycle.Path = relocated_path_factory  # type: ignore[assignment]
    try:
        _ORIGINAL_REVIEWED_TENSILE_CHAIN(
            root=root,
            repository_root=repository_root,
            cycle1=cycle1,
            archive_receipt=archive_receipt,
            selected_records=selected_records,
        )
    finally:
        _lifecycle.Path = original_path_factory


def _walk_authority(value: object, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _DENIED_LATE_TRUE_FIELDS:
                _require(
                    child is False,
                    f"{label} promoted fail-closed authority: {key}",
                )
            if key in _ZERO_LATE_AUTHORITY_FIELDS:
                _require(
                    child == 0 and not isinstance(child, bool),
                    f"{label} promoted zero-valued authority: {key}",
                )
            _walk_authority(child, label=label)
    elif isinstance(value, list):
        for child in value:
            _walk_authority(child, label=label)


def _verify_late_cycle_reports(
    root: Path,
    manifest: Mapping[str, Any],
    cycles: list[dict[str, Any]],
) -> None:
    if len(cycles) < 12:
        return
    reports: dict[str, tuple[dict[str, Any], str]] = {}
    for filename, self_field in _LATE_SELF_HASH_SPECS:
        report = _merge_gate._load(root, filename)
        digest = _merge_gate._verify_self_hash(
            report,
            self_field,
            label=f"late-cycle report {filename}",
        )
        reports[filename] = (report, digest)
        _walk_authority(report, label=f"late-cycle report {filename}")

    cycle_by_index = {
        int(cycle["cycle_index"]): cycle
        for cycle in cycles
        if isinstance(cycle.get("cycle_index"), int)
    }
    for filename, bindings in _LATE_BINDINGS:
        _, digest = reports[filename]
        for scope, cycle_index, field in bindings:
            if scope == "manifest":
                observed = manifest.get(field)
            else:
                _require(
                    cycle_index in cycle_by_index,
                    f"late-cycle binding cycle {cycle_index} is missing",
                )
                observed = cycle_by_index[cycle_index].get(field)
            _require(
                observed == digest,
                f"late-cycle report binding mismatch: {filename} -> {scope}.{field}",
            )


def _verify_transport_partial_output(root: Path, manifest: Mapping[str, Any]) -> None:
    stop = manifest.get("stop")
    if not isinstance(stop, Mapping) or stop.get("reason_code") != _semantic.TRANSPORT_STOP_REASON_CODE:
        return
    report = _merge_gate._load(root, "nist-transport-unavailability.json")
    nist_root = root / "nist-mds2-2923"
    actual = nist_root.is_dir() and any(nist_root.iterdir())
    _require(
        report.get("partial_output_present") is actual,
        "typed NIST transport report partial_output_present disagrees with persisted packages",
    )


def _verify_aggregate_nerdm_metadata(
    root: Path, manifest: Mapping[str, Any]
) -> None:
    receipt_path = root / "nist-network-acquisition-receipt.json"
    if not receipt_path.is_file():
        return
    receipt = _merge_gate._load(root, "nist-network-acquisition-receipt.json")
    metadata_path = (root / "nist-mds2-2923" / "nerdm-metadata.json").resolve(
        strict=True
    )
    try:
        metadata_path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionExactHeadRound3Error(
            "aggregate NERDm metadata escaped the replay root"
        ) from exc
    digest = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    _require(
        receipt.get("metadata_sha256") == digest
        and manifest.get("nist_mds2_2923_metadata_sha256") == digest,
        "aggregate NERDm metadata SHA-256 disagrees with authenticated acquisition receipt",
    )


def _expected_sheet_quality(reviewed_manifest: Mapping[str, Any]) -> dict[str, Any]:
    sheets = reviewed_manifest.get("sheets")
    _require(isinstance(sheets, list) and sheets, "reviewed tensile sheet inventory is missing")
    result: dict[str, Any] = {}
    for item in sheets:
        sheet = _mapping(item, label="reviewed tensile sheet")
        name = sheet.get("sheet_name")
        _require(
            isinstance(name, str) and name and name not in result,
            "reviewed tensile sheet identity is invalid or duplicated",
        )
        result[name] = {
            "measurement_row_count": sheet.get("measurement_row_count"),
            "complete_numeric_row_count": sheet.get("complete_numeric_row_count"),
            "incomplete_numeric_row_count": sheet.get("incomplete_numeric_row_count"),
            "parallel_test_block_count": sheet.get("parallel_test_block_count"),
        }
    return result


def _verify_tensile_quality_projection(root: Path) -> None:
    quality_path = root / "tensile-quality-verification.json"
    reviewed_path = root / _REVIEWED_TENSILE_MANIFEST
    if not quality_path.is_file() or not reviewed_path.is_file():
        return
    quality = _merge_gate._load(root, "tensile-quality-verification.json")
    reviewed = _merge_gate._load(root, _REVIEWED_TENSILE_MANIFEST)
    _require(
        quality.get("reviewed_tensile_manifest_sha256")
        == reviewed.get("manifest_sha256"),
        "tensile quality result is not bound to the reviewed tensile manifest",
    )
    _require(
        quality.get("reviewed_numeric_field_quality_counts")
        == reviewed.get("reviewed_numeric_field_quality_counts"),
        "tensile numeric-field quality projection disagrees with canonical reviewed tensile evidence",
    )
    _require(
        quality.get("sheet_quality") == _expected_sheet_quality(reviewed),
        "tensile sheet-quality projection disagrees with canonical reviewed tensile evidence",
    )


def verify_exact_head_round3_boundaries(output_root: str | Path) -> None:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles: list[dict[str, Any]] = []
    for index, value in enumerate(cycles_value, start=1):
        _require(isinstance(value, dict), f"cycle {index} must be an object")
        cycles.append(value)

    _verify_transport_partial_output(root, manifest)
    _verify_aggregate_nerdm_metadata(root, manifest)
    _verify_tensile_quality_projection(root)
    _verify_late_cycle_reports(root, manifest, cycles)


def install_exact_head_round3_closures() -> None:
    """Install relocation-safe checkout bindings exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _semantic._load_bound_quality_contract = _relocation_safe_quality_contract
    _semantic._verify_qualification = _relocation_safe_qualification
    _lifecycle._verify_reviewed_tensile_chain = (
        _relocation_safe_reviewed_tensile_chain
    )
    _INSTALLED = True


__all__ = [
    "AutonomousProductionExactHeadRound3Error",
    "install_exact_head_round3_closures",
    "verify_exact_head_round3_boundaries",
    "verify_exact_head_round3_preflight",
]
