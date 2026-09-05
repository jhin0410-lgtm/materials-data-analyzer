"""Exact-head closure for the six replay/provenance P2 gaps found on PR #233.

This module deliberately wraps the already-reviewed verifier layers instead of weakening or
replacing their scientific contracts.  It adds only stricter replay/provenance checks:
retained-archive tensile replay, all-cycle authority denial, metadata-derived NIST recorded
provenance, relocation-safe interpretation of historical package paths, and an exact
post-acquisition evidence summary bound to the canonically replayed NIST intake.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import autonomous_production_source_replay_hardening as _source_replay
from .acquisition_record_binding import (
    AcquisitionRecordBindingError,
    authenticate_acquisition_record_binding,
)
from .in625_tensile_reviewed_intake_v2 import (
    In625TensileReviewedIntakeV2Error,
    build_reviewed_in625_tensile_intake_v2,
)
from .nist_pdr_acquisition import discover_nist_pdr_candidates

AutonomousProductionExactHeadP2ClosureError = (
    _source_replay.AutonomousProductionSourceReplayHardeningError
)

_REAL_PATH = Path
_ORIGINAL_TENSILE_REPLAY = _source_replay._verify_reviewed_tensile_source_replay
_ORIGINAL_LATE_CYCLE_AUTHORITY = _source_replay._verify_late_cycle_authority_boundaries
_ORIGINAL_NIST_PACKAGE_AUTHENTICATOR = _source_replay._authenticate_nist_package
_ORIGINAL_SUCCESSFUL_NIST_CHAIN = _merge_gate._verify_successful_nist_chain
_INSTALLED = False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadP2ClosureError(message)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionExactHeadP2ClosureError(
            f"{label} must be valid persisted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{label} root must be an object")
    return value


def _replay_reviewed_tensile_for_every_lifecycle(root: Path) -> None:
    """Canonical row replay is mandatory whether Dataset.zip remains or was cleaned up."""
    persisted_manifest_path = root / _source_replay._REVIEWED_TENSILE_MANIFEST
    persisted_rows_path = root / _source_replay._REVIEWED_TENSILE_ROWS
    manifest_present = persisted_manifest_path.is_file()
    rows_present = persisted_rows_path.is_file()
    if not manifest_present and not rows_present:
        # Early transport-stop fixtures may legitimately retain only the authenticated raw
        # archive and no reviewed derivative yet. Preserve the reviewed raw-archive verifier.
        _ORIGINAL_TENSILE_REPLAY(root)
        return
    _require(
        manifest_present and rows_present,
        "reviewed tensile evidence is incomplete for canonical source replay",
    )

    repository_root = _merge_gate._trusted_repository_root().resolve(strict=True)
    policy_path = (
        repository_root / _source_replay._REVIEWED_TENSILE_POLICY
    ).resolve(strict=True)
    _source_replay._inside(
        policy_path, repository_root, label="reviewed tensile policy"
    )
    policy = _source_replay._load_json(
        policy_path, label="reviewed tensile policy"
    )

    def selected_source(record_name: str) -> Path:
        record = _source_replay._mapping(
            policy.get(record_name), label=f"reviewed tensile policy {record_name}"
        )
        member = record.get("archive_member_path")
        _require(
            isinstance(member, str) and member,
            f"reviewed tensile {record_name} archive member is invalid",
        )
        member_path = PurePosixPath(member)
        _require(
            not member_path.is_absolute()
            and all(part not in {"", ".", ".."} for part in member_path.parts),
            f"reviewed tensile {record_name} archive member is unsafe",
        )
        path = (
            root / _source_replay._SELECTED_SOURCE_ROOT / Path(*member_path.parts)
        ).resolve(strict=True)
        _source_replay._inside(path, root, label=f"reviewed tensile {record_name}")
        raw = path.read_bytes()
        _require(
            record.get("sha256") == hashlib.sha256(raw).hexdigest()
            and record.get("size_bytes") == len(raw),
            f"reviewed tensile {record_name} source bytes drifted from tracked policy",
        )
        return path

    workbook_path = selected_source("workbook")
    readme_path = selected_source("documentation")
    persisted_manifest = _source_replay._load_json(
        persisted_manifest_path, label="persisted reviewed tensile manifest"
    )
    persisted_row_bytes = persisted_rows_path.read_bytes()

    try:
        with TemporaryDirectory(prefix="mda-reviewed-tensile-replay-") as temporary:
            replay_dir = Path(temporary) / "reviewed-tensile"
            replay_manifest = build_reviewed_in625_tensile_intake_v2(
                workbook_path=workbook_path,
                readme_path=readme_path,
                policy_path=policy_path,
                output_dir=replay_dir,
            )
            replay_row_bytes = (
                replay_dir / "reviewed_tensile_rows.v2.jsonl"
            ).read_bytes()
    except (In625TensileReviewedIntakeV2Error, OSError) as exc:
        raise AutonomousProductionExactHeadP2ClosureError(
            "reviewed tensile canonical source replay failed"
        ) from exc

    _source_replay._require_tensile_replay_match(
        persisted_manifest=persisted_manifest,
        persisted_row_bytes=persisted_row_bytes,
        replay_manifest=replay_manifest,
        replay_row_bytes=replay_row_bytes,
    )


def _verify_all_success_cycles(cycles: list[dict[str, Any]]) -> None:
    """Preserve explicit cycle 4/6/8 checks and scan authority through the terminal cycle."""
    _ORIGINAL_LATE_CYCLE_AUTHORITY(cycles)
    for cycle in cycles[8:]:
        cycle_index = int(cycle["cycle_index"])
        _source_replay._scan_authority(cycle, cycle_index=cycle_index)


def _metadata_candidate(*, metadata_bytes: bytes, path: str) -> Mapping[str, Any]:
    try:
        candidates = discover_nist_pdr_candidates(
            metadata_bytes=metadata_bytes,
            product_id=_source_replay.NIST_PRODUCT_ID,
            filepaths=list(_source_replay.EXPECTED_FILES),
            evidence_role="response_compatible_geometry_evidence",
        )
    except Exception as exc:
        raise AutonomousProductionExactHeadP2ClosureError(
            "exact NIST metadata candidate replay failed"
        ) from exc
    by_path = {
        candidate.get("artifact_path"): candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
    }
    _require(
        set(by_path) == set(_source_replay.EXPECTED_FILES),
        "exact NIST metadata candidate set drifted during provenance replay",
    )
    candidate = by_path.get(path)
    _require(
        isinstance(candidate, Mapping),
        f"exact NIST metadata candidate missing during provenance replay: {path}",
    )
    return candidate


def _authenticate_nist_package_against_metadata(
    *,
    root: Path,
    path: str,
    rule: Mapping[str, Any],
    package_index: int,
    top_receipt: Mapping[str, Any],
    expected_metadata_sha256: str = _source_replay.EXPECTED_METADATA_SHA256,
) -> tuple[bytes, bytes]:
    """Run the existing exact-byte binder, then bind recorded values to NERDm-derived values."""
    raw, metadata_bytes = _ORIGINAL_NIST_PACKAGE_AUTHENTICATOR(
        root=root,
        path=path,
        rule=rule,
        package_index=package_index,
        top_receipt=top_receipt,
        expected_metadata_sha256=expected_metadata_sha256,
    )
    candidate = _metadata_candidate(metadata_bytes=metadata_bytes, path=path)
    package = root / "nist-mds2-2923" / f"artifact-{package_index:02d}"
    manifest_bytes = (package / "acquisition_manifest.json").read_bytes()
    declaration_bytes = (package / "acquisition_declaration.json").read_bytes()
    try:
        authenticated = authenticate_acquisition_record_binding(
            evidence_bytes=raw,
            acquisition_manifest_bytes=manifest_bytes,
            acquisition_declaration_bytes=declaration_bytes,
        )
    except AcquisitionRecordBindingError as exc:
        raise AutonomousProductionExactHeadP2ClosureError(
            f"NIST canonical acquisition-record binding failed: {path}"
        ) from exc

    _require(
        authenticated.get("recorded_source_system") == candidate.get("source_system")
        and authenticated.get("recorded_source_version") == candidate.get("source_version")
        and authenticated.get("recorded_retrieval_endpoint")
        == candidate.get("retrieval_endpoint")
        and authenticated.get("recorded_retrieval_status")
        == "downloaded_checksum_verified"
        and authenticated.get("recorded_network_performed") is True,
        f"NIST recorded provenance values disagree with authenticated metadata candidate: {path}",
    )
    return raw, metadata_bytes


def _safe_recorded_suffix(
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
        f"{label} does not end in the exact replay-root-relative path",
    )
    return value


def _validate_relocation_safe_paths(
    root: Path, receipt: Mapping[str, Any]
) -> dict[str, Path]:
    """Authenticate historical path structure while resolving current locators from replay root."""
    mapping: dict[str, Path] = {}
    nist_root = (root / "nist-mds2-2923").resolve(strict=True)

    metadata_recorded = _safe_recorded_suffix(
        receipt.get("metadata_path"),
        expected_parts=("nist-mds2-2923", "nerdm-metadata.json"),
        label="NIST metadata historical path",
    )
    metadata_current = (nist_root / "nerdm-metadata.json").resolve(strict=True)
    _source_replay._inside(metadata_current, root, label="NIST replay metadata")
    mapping[metadata_recorded] = metadata_current

    artifact_paths = receipt.get("artifact_paths")
    receipts = receipt.get("receipts")
    _require(
        isinstance(artifact_paths, Mapping)
        and set(artifact_paths) == set(_source_replay.EXPECTED_FILES),
        "NIST historical artifact path set drifted",
    )
    _require(
        isinstance(receipts, list)
        and len(receipts) == len(_source_replay.EXPECTED_FILES),
        "NIST historical per-file receipt set drifted",
    )

    for index, path in enumerate(_source_replay.EXPECTED_FILES, start=1):
        package_parts = ("nist-mds2-2923", f"artifact-{index:02d}")
        package = (nist_root / f"artifact-{index:02d}").resolve(strict=True)
        artifact = (package / path).resolve(strict=True)
        _source_replay._inside(package, nist_root, label=f"NIST replay package {index}")
        _source_replay._inside(artifact, package, label=f"NIST replay artifact {path}")

        recorded_artifact = _safe_recorded_suffix(
            artifact_paths[path],
            expected_parts=(*package_parts, path),
            label=f"NIST artifact historical path {path}",
        )
        top = receipts[index - 1]
        _require(
            isinstance(top, Mapping),
            f"NIST historical per-file receipt {index} must be an object",
        )
        recorded_package = _safe_recorded_suffix(
            top.get("package_directory"),
            expected_parts=package_parts,
            label=f"NIST package historical path {path}",
        )
        mapping[recorded_artifact] = artifact
        mapping[recorded_package] = package

    return mapping


def _expected_verified_new_evidence(intake: Mapping[str, Any]) -> dict[str, Any]:
    inventory = intake.get("in625_inventory")
    measurements = intake.get("measurements")
    _require(
        isinstance(inventory, Mapping) and isinstance(measurements, list),
        "canonical NIST intake lacks inventory or measurement rows",
    )
    materials = {
        row.get("material")
        for row in measurements
        if isinstance(row, Mapping) and isinstance(row.get("material"), str)
    }
    _require(materials == {"IN625"}, "canonical NIST intake material identity drifted")
    source = intake.get("source")
    _require(isinstance(source, Mapping), "canonical NIST intake source is invalid")
    _require(
        source.get("product_id") == _source_replay.NIST_PRODUCT_ID,
        "canonical NIST intake product identity drifted",
    )
    return {
        "dataset_local_physical_track_count": inventory.get("physical_track_count"),
        "geometry_response_compatibility_established": True,
        "machine_measurement_counts": inventory.get("machine_measurement_counts"),
        "machine_physical_track_counts": inventory.get("machine_physical_track_counts"),
        "material": "IN625",
        "measurement_row_count": inventory.get("measurement_row_count"),
        "response_semantics": ["melt_pool_width", "melt_pool_depth"],
        "row_level_authority": "Data sheet",
        "source": f"NIST PDR {source.get('product_id')}",
        "source_metadata_conflict_count": inventory.get(
            "source_track_metadata_conflict_count"
        ),
        "summary_role": "incomplete_derived_view",
    }


def _verify_canonical_post_acquisition_summary(root: Path) -> None:
    """Require rediagnosis evidence summary to be exactly derived from replayed source intake."""
    _source_replay._verify_successful_nist_source_replay(root)
    intake = _load_json(
        root / "nist-scientific-intake.json", label="persisted NIST scientific intake"
    )
    rediagnosis = _load_json(
        root / "nist-post-acquisition-rediagnosis.json",
        label="persisted NIST post-acquisition rediagnosis",
    )
    expected = _expected_verified_new_evidence(intake)
    _require(
        rediagnosis.get("verified_new_evidence") == expected,
        "NIST post-acquisition verified_new_evidence does not match canonical intake",
    )


def _relocation_safe_successful_nist_chain(
    root: Path,
    manifest: Mapping[str, Any],
    cycles: list[dict[str, Any]],
) -> None:
    receipt = _merge_gate._load(root, "nist-network-acquisition-receipt.json")
    path_mapping = _validate_relocation_safe_paths(root, receipt)

    original_path_factory = _merge_gate.Path

    def relocated_path_factory(value: object = ".") -> Path:
        if isinstance(value, str) and value in path_mapping:
            return path_mapping[value]
        return _REAL_PATH(value)

    _merge_gate.Path = relocated_path_factory  # type: ignore[assignment]
    try:
        _ORIGINAL_SUCCESSFUL_NIST_CHAIN(root, manifest, cycles)
    finally:
        _merge_gate.Path = original_path_factory

    _verify_canonical_post_acquisition_summary(root)


def install_exact_head_p2_closures() -> None:
    """Install stricter exact-head gates once, before any public live verification dispatch."""
    global _INSTALLED
    if _INSTALLED:
        return

    _source_replay._DENIED_TRUE_AUTHORITY_FIELDS.add(
        "global_evidence_unavailability_claimed"
    )
    _source_replay._verify_reviewed_tensile_source_replay = (
        _replay_reviewed_tensile_for_every_lifecycle
    )
    _source_replay._verify_late_cycle_authority_boundaries = _verify_all_success_cycles
    _source_replay._authenticate_nist_package = _authenticate_nist_package_against_metadata
    _merge_gate._verify_successful_nist_chain = _relocation_safe_successful_nist_chain
    _INSTALLED = True


__all__ = [
    "AutonomousProductionExactHeadP2ClosureError",
    "install_exact_head_p2_closures",
]
