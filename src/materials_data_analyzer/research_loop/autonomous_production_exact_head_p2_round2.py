"""Second exact-head fail-closed closure for PR #233.

This layer addresses fresh P2 findings from the Codex review of exact head
``7f0dc87027bcd8ae992455a67b7c238a6074e208``.  It only adds stricter
verification: reviewed-tensile derivative presence when cycle 1 binds those
artifacts, relocation-safe interpretation of the historical Zenodo archive
path, predecessor automatic-execution denial, exact post-acquisition evidence
lanes, and authenticated cycle-4 geometry/multisource provenance.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from . import autonomous_production_exact_head_p2_closure as _round1
from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_merge_gate_lifecycle as _lifecycle

AutonomousProductionExactHeadRound2Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_REAL_PATH = Path
_ORIGINAL_ZENODO_POST_CLEANUP = _lifecycle._verify_receipt_without_transient_archive
_INSTALLED = False

_EXPECTED_EVIDENCE_LANES = [
    "authoritative_row_level_dataset",
    "paper_and_supplementary_material",
    "official_technical_report",
    "official_calibration_or_metrology_documentation",
    "characterization_evidence",
    "other_provenance_verifiable_physical_evidence",
]
_EXPECTED_PAPER_EVIDENCE_ROLE = (
    "May establish or challenge protocol, calibration, machine, spot-size, "
    "surface-state, and condition-mapping claims; literature-only claims are "
    "not silently promoted to row-level measurement authority."
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound2Error(message)


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
        f"{label} does not end in the exact historical production suffix",
    )
    return value


def _relocation_safe_zenodo_post_cleanup(
    *, root: Path, cycle1: Mapping[str, Any]
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Resolve the authenticated historical Dataset.zip locator from replay root."""
    receipt = _merge_gate._load(root, "network-acquisition-receipt.json")
    archive = _mapping(receipt.get("archive"), label="cycle-1 Zenodo archive")
    recorded = _safe_historical_suffix(
        archive.get("path"),
        expected_parts=("autonomous-in625-production", "Dataset.zip"),
        label="cycle-1 Zenodo historical archive path",
    )
    current = (root / "Dataset.zip").resolve(strict=False)
    original_path_factory = _lifecycle.Path

    def relocated_path_factory(value: object = ".") -> Path:
        if isinstance(value, str) and value == recorded:
            return current
        return _REAL_PATH(value)

    _lifecycle.Path = relocated_path_factory  # type: ignore[assignment]
    try:
        return _ORIGINAL_ZENODO_POST_CLEANUP(root=root, cycle1=cycle1)
    finally:
        _lifecycle.Path = original_path_factory


def _verify_bound_reviewed_tensile_presence(
    root: Path, cycles: list[dict[str, Any]]
) -> None:
    _require(bool(cycles), "autonomous production cycles are missing")
    cycle1 = cycles[0]
    binding = cycle1.get("reviewed_tensile_manifest_sha256")
    manifest_path = root / _round1._source_replay._REVIEWED_TENSILE_MANIFEST
    rows_path = root / _round1._source_replay._REVIEWED_TENSILE_ROWS
    manifest_present = manifest_path.is_file()
    rows_present = rows_path.is_file()

    if isinstance(binding, str) and binding:
        _require(
            manifest_present and rows_present,
            "cycle 1 binds reviewed tensile evidence but persisted derivatives are missing",
        )
        _round1._replay_reviewed_tensile_for_every_lifecycle(root)
        return

    _require(
        len(cycles) <= 3,
        "post-transport production outcome is missing the cycle-1 reviewed tensile binding",
    )
    if manifest_present or rows_present:
        _round1._replay_reviewed_tensile_for_every_lifecycle(root)


def _verify_predecessor_execution_boundary(root: Path) -> None:
    rediagnosis = _merge_gate._load(root, "quality-aware-rediagnosis.json")
    next_action = _mapping(
        rediagnosis.get("next_action"), label="quality-aware rediagnosis next_action"
    )
    _require(
        next_action.get("automatic_execution_authorized") is False,
        "quality-aware predecessor rediagnosis granted automatic execution",
    )


def _verify_post_acquisition_lane_contract(root: Path) -> None:
    path = root / "nist-post-acquisition-rediagnosis.json"
    if not path.is_file():
        return
    rediagnosis = _merge_gate._load(root, "nist-post-acquisition-rediagnosis.json")
    next_action = _mapping(
        rediagnosis.get("next_action"), label="NIST post-acquisition next_action"
    )
    _require(
        next_action.get("eligible_evidence_lanes") == _EXPECTED_EVIDENCE_LANES,
        "NIST post-acquisition eligible evidence lanes drifted",
    )
    _require(
        next_action.get("paper_evidence_role") == _EXPECTED_PAPER_EVIDENCE_ROLE,
        "NIST post-acquisition paper evidence role drifted",
    )


def _verify_cycle4_artifacts(root: Path, cycles: list[dict[str, Any]]) -> None:
    if len(cycles) < 4:
        return
    cycle4 = cycles[3]
    _require(cycle4.get("cycle_index") == 4, "cycle-4 index drifted")

    mapping = _merge_gate._load(root, "geometry-condition-mapping-assessment.json")
    mapping_sha = _merge_gate._verify_self_hash(
        mapping,
        "report_sha256_without_self_field",
        label="geometry-condition mapping assessment",
    )
    _require(
        cycle4.get("mapping_assessment_sha256") == mapping_sha,
        "cycle 4 geometry mapping digest binding mismatch",
    )
    boundary = _mapping(
        mapping.get("scientific_boundary"), label="geometry mapping scientific boundary"
    )
    for key in (
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "numerical_cross_source_comparison_performed",
        "positive_scientific_closeout",
        "scientific_status_changed",
        "source_acquisition_success_interpreted_as_scientific_support",
    ):
        _require(
            boundary.get(key) is False,
            f"geometry mapping scientific boundary promoted authority: {key}",
        )

    sources = _merge_gate._load(root, "multisource-source-acquisition.json")
    sources_sha = _merge_gate._verify_self_hash(
        sources,
        "report_sha256_without_self_field",
        label="multisource source acquisition",
    )
    _require(
        cycle4.get("source_acquisition_report_sha256") == sources_sha,
        "cycle 4 multisource acquisition digest binding mismatch",
    )
    records = sources.get("sources")
    _require(isinstance(records, list), "multisource source records must be a list")
    _require(
        sources.get("source_count") == len(records) == 8,
        "multisource source record count drifted",
    )
    _require(
        sources.get("paper_claims_promoted_to_row_level_authority") is False
        and sources.get("scientific_status_changed") is False,
        "multisource aggregate authority boundary drifted",
    )
    for index, record in enumerate(records, start=1):
        item = _mapping(record, label=f"multisource source {index}")
        _require(
            item.get("row_level_measurement_authority") is False,
            f"multisource source {index} gained row-level measurement authority",
        )
        _require(
            item.get("scientific_status_changed") is False,
            f"multisource source {index} changed scientific status",
        )


def verify_exact_head_round2_boundaries(output_root: str | Path) -> None:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles: list[dict[str, Any]] = []
    for index, value in enumerate(cycles_value, start=1):
        _require(isinstance(value, dict), f"cycle {index} must be an object")
        cycles.append(value)

    _verify_bound_reviewed_tensile_presence(root, cycles)
    _verify_predecessor_execution_boundary(root)
    _verify_post_acquisition_lane_contract(root)
    _verify_cycle4_artifacts(root, cycles)


def install_exact_head_round2_closures() -> None:
    """Install relocation-safe Zenodo post-cleanup replay exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _lifecycle._verify_receipt_without_transient_archive = (
        _relocation_safe_zenodo_post_cleanup
    )
    _INSTALLED = True


__all__ = [
    "AutonomousProductionExactHeadRound2Error",
    "install_exact_head_round2_closures",
    "verify_exact_head_round2_boundaries",
]
