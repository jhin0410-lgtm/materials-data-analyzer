"""Lifecycle-aware final merge-gate verification for autonomous production.

The production driver deliberately removes the 180 MB Zenodo ``Dataset.zip`` after it has
verified the pinned archive and materialized the bounded reviewed evidence used downstream.
The previous final hardening layer incorrectly required that transient raw archive to remain
present at final verification time.  This wrapper preserves every existing final merge-gate
check while replacing only the cycle-1 archive check with a two-mode contract:

* if the raw archive is still present, replay the existing byte-level verifier unchanged;
* after the producer's explicit cleanup, require the acquisition receipt, self-hashed archive
  inventory, cycle-bound reviewed tensile manifest, tracked tensile policy, exact extracted
  workbook/README bytes, and row artifact to agree before accepting the evidence lineage.

No source identity, scientific authority, comparability, or downstream-use gate is widened.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from . import autonomous_production_merge_gate_hardening as _base

AutonomousProductionMergeGateHardeningError = (
    _base.AutonomousProductionMergeGateHardeningError
)

_REVIEWED_TENSILE_MANIFEST = "reviewed-tensile/reviewed_tensile_manifest.v2.json"
_REVIEWED_TENSILE_ROWS = "reviewed-tensile/reviewed_tensile_rows.v2.jsonl"
_ARCHIVE_MANIFEST = "archive-manifest.json"
_SELECTED_SOURCE_ROOT = "selected-source-files"
_REVIEWED_TENSILE_POLICY = _base._EXPECTED_BINDINGS[
    "zenodo_reviewed_tensile_contract"
]


def _load_trusted_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionMergeGateHardeningError(
            f"{label} must be valid tracked UTF-8 JSON"
        ) from exc
    _base._require(isinstance(value, dict), f"{label} root must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_receipt_without_transient_archive(
    *, root: Path, cycle1: Mapping[str, Any]
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    receipt = _base._load(root, "network-acquisition-receipt.json")
    receipt_sha = _base._verify_self_hash(
        receipt,
        "receipt_sha256",
        label="cycle-1 network acquisition receipt",
    )
    _base._require(
        cycle1.get("network_receipt_sha256") == receipt_sha,
        "cycle 1 network receipt binding mismatch",
    )
    _base._require(
        cycle1.get("network_authorization_sha256")
        == receipt.get("authorization_sha256"),
        "cycle 1 network authorization binding mismatch",
    )

    archive = _base._mapping(receipt.get("archive"), "cycle-1 Zenodo archive")
    raw_archive_path = archive.get("path")
    _base._require(
        isinstance(raw_archive_path, str) and raw_archive_path,
        "cycle-1 Zenodo archive path is invalid",
    )
    archive_path = Path(raw_archive_path).expanduser().resolve(strict=False)
    expected_archive_path = (root / "Dataset.zip").resolve(strict=False)
    _base._require(
        archive_path == expected_archive_path,
        "cycle-1 Zenodo archive path drifted",
    )
    _base._inside(archive_path, root, label="cycle-1 Zenodo archive")
    _base._require(
        not archive_path.exists(),
        "cycle-1 post-cleanup verification received an unexpected raw archive",
    )
    _base._require(
        receipt.get("schema_version") == "1.0"
        and receipt.get("policy_version") == "1.0"
        and receipt.get("source_id") == _base._EXPECTED_ZENODO_SOURCE_ID
        and receipt.get("zenodo_record_id") == _base._EXPECTED_ZENODO_RECORD_ID
        and archive.get("file_name") == "Dataset.zip"
        and archive.get("requested_url") == _base._EXPECTED_ZENODO_ARCHIVE_URL
        and archive.get("final_url") == _base._EXPECTED_ZENODO_ARCHIVE_URL
        and archive.get("content_type") == "application/octet-stream"
        and archive.get("provider_md5") == _base._EXPECTED_ZENODO_ARCHIVE_MD5
        and archive.get("sha256") == _base._EXPECTED_ZENODO_ARCHIVE_SHA256
        and archive.get("size_bytes") == _base._EXPECTED_ZENODO_ARCHIVE_SIZE_BYTES,
        "cycle-1 Zenodo source identity drifted",
    )
    _base._require(
        receipt.get("network_access_performed") is True
        and receipt.get("network_execution_authorized") is True
        and receipt.get("provider_checksum_verified") is True
        and receipt.get("project_sha256_verified") is True
        and receipt.get("byte_count_verified") is True
        and receipt.get("exact_host_restriction_enforced") is True,
        "cycle-1 acquisition provenance was not fully authenticated",
    )
    boundary = _base._mapping(
        receipt.get("scientific_boundary"),
        "cycle-1 acquisition scientific boundary",
    )
    _base._require(
        boundary.get("automatic_scientific_promotion") is False
        and boundary.get("direct_nist_condition_comparability_established") is False
        and boundary.get("empirical_model_validation_established") is False
        and boundary.get("hypothesis_truth_established") is False
        and boundary.get("measurement_semantics_interpreted") is False
        and boundary.get("positive_scientific_closeout_established") is False
        and boundary.get("replicate_independence_established") is False
        and boundary.get("sample_identity_established") is False
        and boundary.get("source_provenance_established_by_successful_download")
        is True,
        "cycle-1 acquisition receipt widened scientific authority",
    )
    return receipt, archive


def _verify_archive_manifest(
    *,
    root: Path,
    archive_receipt: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    manifest = _base._load(root, _ARCHIVE_MANIFEST)
    _base._verify_self_hash(
        manifest,
        "manifest_sha256",
        label="cycle-1 verified archive manifest",
    )
    archive = _base._mapping(
        manifest.get("archive"), "cycle-1 verified archive manifest archive"
    )
    _base._require(
        archive.get("file_name") == "Dataset.zip"
        and archive.get("size_bytes") == archive_receipt.get("size_bytes")
        and archive.get("provider_md5") == archive_receipt.get("provider_md5")
        and archive.get("sha256") == archive_receipt.get("sha256")
        and archive.get("sha256_previously_pinned") is True,
        "cycle-1 archive manifest disagrees with authenticated acquisition receipt",
    )
    boundary = _base._mapping(
        manifest.get("scientific_boundary"),
        "cycle-1 archive manifest scientific boundary",
    )
    _base._require(
        boundary.get("authority_class") == "source_artifact_only"
        and boundary.get("source_provenance_established") is True
        and boundary.get("artifact_bytes_verified") is True
        and boundary.get("direct_nist_condition_comparability_established") is False
        and boundary.get("empirical_model_validation_established") is False
        and boundary.get("hypothesis_truth_established") is False
        and boundary.get("positive_scientific_closeout_established") is False
        and boundary.get("automatic_scientific_promotion") is False,
        "cycle-1 archive manifest widened scientific authority",
    )
    selected = manifest.get("selected_tabular_files")
    _base._require(
        isinstance(selected, list) and selected,
        "cycle-1 archive manifest omitted selected source files",
    )
    result: dict[str, Mapping[str, Any]] = {}
    for item in selected:
        record = _base._mapping(item, "cycle-1 archive selected source record")
        relative = record.get("path")
        _base._require(
            isinstance(relative, str) and relative and relative not in result,
            "cycle-1 archive manifest selected-source path is invalid or duplicated",
        )
        result[relative] = record
    return result


def _verify_reviewed_tensile_chain(
    *,
    root: Path,
    repository_root: Path,
    cycle1: Mapping[str, Any],
    archive_receipt: Mapping[str, Any],
    selected_records: Mapping[str, Mapping[str, Any]],
) -> None:
    policy_path = (repository_root / _REVIEWED_TENSILE_POLICY).resolve(strict=True)
    _base._inside(policy_path, repository_root, label="reviewed tensile policy")
    policy = _load_trusted_json(policy_path, label="reviewed tensile policy")
    workbook_policy = _base._mapping(
        policy.get("workbook"), "reviewed tensile policy workbook"
    )
    documentation_policy = _base._mapping(
        policy.get("documentation"), "reviewed tensile policy documentation"
    )
    scientific_policy = _base._mapping(
        policy.get("scientific_boundaries"),
        "reviewed tensile policy scientific boundaries",
    )
    _base._require(
        policy.get("schema_version") == "1.0"
        and policy.get("source_id") == _base._EXPECTED_ZENODO_SOURCE_ID
        and policy.get("source_archive_sha256")
        == _base._EXPECTED_ZENODO_ARCHIVE_SHA256
        and scientific_policy.get("parallel_tests_imply_statistical_independence")
        is False
        and scientific_policy.get("direct_nist_condition_comparability_established")
        is False
        and scientific_policy.get("empirical_model_validation_established") is False
        and scientific_policy.get("hypothesis_truth_established") is False
        and scientific_policy.get("positive_scientific_closeout_established")
        is False
        and scientific_policy.get("automatic_scientific_promotion") is False,
        "reviewed tensile policy identity or scientific authority drifted",
    )

    manifest = _base._load(root, _REVIEWED_TENSILE_MANIFEST)
    manifest_sha = _base._verify_self_hash(
        manifest,
        "manifest_sha256",
        label="reviewed tensile manifest",
    )
    _base._require(
        cycle1.get("reviewed_tensile_manifest_sha256") == manifest_sha,
        "cycle 1 reviewed tensile manifest binding mismatch",
    )
    manifest_policy = _base._mapping(
        manifest.get("policy"), "reviewed tensile manifest policy"
    )
    manifest_workbook = _base._mapping(
        manifest.get("workbook"), "reviewed tensile manifest workbook"
    )
    manifest_documentation = _base._mapping(
        manifest.get("documentation"), "reviewed tensile manifest documentation"
    )
    reviewed_semantics = _base._mapping(
        manifest.get("reviewed_semantics"), "reviewed tensile semantics"
    )
    evidence_quality = _base._mapping(
        manifest.get("evidence_quality"), "reviewed tensile evidence quality"
    )
    boundaries = _base._mapping(
        manifest.get("scientific_boundaries"),
        "reviewed tensile scientific boundaries",
    )
    _base._require(
        manifest.get("schema_version") == "2.0"
        and manifest.get("source_id") == _base._EXPECTED_ZENODO_SOURCE_ID
        and manifest.get("source_archive_sha256") == archive_receipt.get("sha256")
        and manifest.get("measurement_row_count") == 200289
        and manifest.get("complete_numeric_measurement_row_count") == 200288
        and manifest.get("incomplete_numeric_measurement_row_count") == 1
        and manifest.get("parallel_test_block_count") == 19
        and reviewed_semantics.get("missing_values_imputed") is False
        and reviewed_semantics.get("non_numeric_values_coerced") is False
        and reviewed_semantics.get("parallel_test_independence_established") is False
        and evidence_quality.get("missingness_mechanism_established") is False
        and boundaries.get("real_row_level_external_measurements_observed") is True
        and boundaries.get("replicate_independence_established") is False
        and boundaries.get("direct_nist_condition_comparability_established") is False
        and boundaries.get("empirical_model_validation_established") is False
        and boundaries.get("hypothesis_truth_established") is False
        and boundaries.get("positive_scientific_closeout_established") is False
        and boundaries.get("automatic_scientific_promotion") is False,
        "reviewed tensile evidence identity or scientific boundary drifted",
    )
    policy_raw = policy_path.read_bytes()
    _base._require(
        Path(str(manifest_policy.get("path"))).expanduser().resolve(strict=True)
        == policy_path
        and manifest_policy.get("sha256") == hashlib.sha256(policy_raw).hexdigest(),
        "reviewed tensile manifest is not bound to the tracked policy bytes",
    )

    expected_bindings = (
        ("workbook", workbook_policy, manifest_workbook),
        ("documentation", documentation_policy, manifest_documentation),
    )
    for label, policy_record, manifest_record in expected_bindings:
        member = policy_record.get("archive_member_path")
        _base._require(
            isinstance(member, str) and member,
            f"reviewed tensile {label} archive member is invalid",
        )
        member_path = PurePosixPath(member)
        _base._require(
            not member_path.is_absolute()
            and all(part not in {"", ".", ".."} for part in member_path.parts),
            f"reviewed tensile {label} archive member is unsafe",
        )
        expected_path = (
            root / _SELECTED_SOURCE_ROOT / Path(*member_path.parts)
        ).resolve(strict=True)
        _base._inside(expected_path, root, label=f"reviewed tensile {label}")
        observed_path = Path(str(manifest_record.get("path"))).expanduser().resolve(
            strict=True
        )
        raw = expected_path.read_bytes()
        expected_sha = policy_record.get("sha256")
        expected_bytes = policy_record.get("size_bytes")
        _base._require(
            observed_path == expected_path
            and manifest_record.get("sha256") == expected_sha
            and manifest_record.get("bytes") == expected_bytes
            and len(raw) == expected_bytes
            and hashlib.sha256(raw).hexdigest() == expected_sha,
            f"reviewed tensile {label} bytes drifted from tracked policy",
        )
        archive_record = selected_records.get(member)
        _base._require(
            isinstance(archive_record, Mapping)
            and archive_record.get("sha256") == expected_sha
            and archive_record.get("size_bytes") == expected_bytes,
            f"archive manifest does not bind the reviewed tensile {label} bytes",
        )

    row_artifact = _base._mapping(
        manifest.get("row_artifact"), "reviewed tensile row artifact"
    )
    row_path = Path(str(row_artifact.get("path"))).expanduser().resolve(strict=True)
    expected_row_path = (root / _REVIEWED_TENSILE_ROWS).resolve(strict=True)
    _base._require(
        row_path == expected_row_path,
        "reviewed tensile row artifact path drifted",
    )
    _base._inside(row_path, root, label="reviewed tensile row artifact")
    _base._require(
        row_artifact.get("row_count") == 200289
        and row_artifact.get("bytes") == row_path.stat().st_size
        and row_artifact.get("sha256") == _sha256_file(row_path),
        "reviewed tensile row artifact bytes or row count drifted",
    )


def _verify_cycle1_lifecycle(
    *,
    root: Path,
    repository_root: Path,
    cycle1: Mapping[str, Any],
) -> None:
    raw_archive = (root / "Dataset.zip").resolve(strict=False)
    if raw_archive.exists():
        # Preserve the original byte-level replay unchanged whenever raw bytes remain.
        _base._verify_cycle1_network_receipt(root, cycle1)
        return

    _, archive_receipt = _verify_receipt_without_transient_archive(
        root=root,
        cycle1=cycle1,
    )
    selected = _verify_archive_manifest(
        root=root,
        archive_receipt=archive_receipt,
    )
    _verify_reviewed_tensile_chain(
        root=root,
        repository_root=repository_root,
        cycle1=cycle1,
        archive_receipt=archive_receipt,
        selected_records=selected,
    )


def _verify_checkout_bindings(
    root: Path, cycles: list[dict[str, Any]]
) -> Path:
    repository_root = _base._trusted_repository_root().resolve(strict=True)
    _base._inside(root, repository_root, label="autonomous production output")

    quality = _base._load(root, "tensile-quality-verification.json")
    quality_binding = _base._mapping(
        quality.get("quality_contract"), "tensile quality quality_contract"
    )
    raw_quality_path = quality_binding.get("path")
    _base._require(
        isinstance(raw_quality_path, str) and raw_quality_path,
        "quality contract path is invalid",
    )
    quality_path = Path(raw_quality_path).expanduser().resolve(strict=True)
    expected_quality_path = (
        repository_root / _base._EXPECTED_QUALITY_CONTRACT
    ).resolve(strict=True)
    _base._require(
        quality_path == expected_quality_path,
        "quality contract is not bound to the trusted checkout",
    )
    raw_quality = quality_path.read_bytes()
    _base._require(
        quality_binding.get("bytes") == len(raw_quality),
        "quality contract byte count mismatch",
    )
    _base._require(
        quality_binding.get("sha256") == hashlib.sha256(raw_quality).hexdigest(),
        "quality contract SHA-256 mismatch against trusted checkout",
    )

    qualification = _base._load(root, "nist-network-policy-qualification.json")
    raw_frontier = qualification.get("frontier_path")
    _base._require(
        isinstance(raw_frontier, str) and raw_frontier,
        "NIST qualification frontier path is invalid",
    )
    frontier = Path(raw_frontier).expanduser().resolve(strict=True)
    expected_frontier = (repository_root / _base.FRONTIER_PATH).resolve(strict=True)
    _base._require(
        frontier == expected_frontier,
        "NIST qualification frontier is not bound to trusted checkout",
    )
    _base._require(
        qualification.get("frontier_sha256")
        == hashlib.sha256(frontier.read_bytes()).hexdigest(),
        "NIST qualification frontier SHA-256 mismatch against trusted checkout",
    )

    assessment = _base._load(root, "physical-comparability-assessment.json")
    bindings = _base._mapping(
        assessment.get("evidence_bindings"),
        "physical comparability evidence bindings",
    )
    _base._require(
        set(bindings) == set(_base._EXPECTED_BINDINGS),
        "physical comparability binding set drifted",
    )
    for key, relative in _base._EXPECTED_BINDINGS.items():
        _base._verify_bound_file(
            repository_root=repository_root,
            binding=bindings.get(key),
            expected_path=relative,
            label=f"physical comparability binding {key}",
        )

    _base._require(cycles, "autonomous production cycle chain is empty")
    _verify_cycle1_lifecycle(
        root=root,
        repository_root=repository_root,
        cycle1=cycles[0],
    )
    return repository_root


def verify_final_merge_gate_boundaries(output_root: str | Path) -> None:
    """Run the original final gate with the producer's archive-cleanup lifecycle."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _base._load(root, "autonomous-production-manifest.json")
    cycles_raw = manifest.get("cycles")
    _base._require(
        isinstance(cycles_raw, list) and cycles_raw,
        "autonomous production cycles are invalid",
    )
    cycles: list[dict[str, Any]] = []
    for index, cycle in enumerate(cycles_raw, start=1):
        _base._require(isinstance(cycle, dict), f"cycle {index} must be an object")
        cycles.append(dict(cycle))

    _verify_checkout_bindings(root, cycles)

    stop = _base._mapping(manifest.get("stop"), "autonomous production stop")
    if stop.get("reason_code") == _base.TRANSPORT_STOP_REASON_CODE:
        return

    if (
        len(cycles) >= 3
        and cycles[2].get("selected_action_class") == _base.NIST_ACTION_CLASS
    ):
        _base._verify_successful_nist_chain(root, manifest, cycles)


__all__ = [
    "AutonomousProductionMergeGateHardeningError",
    "verify_final_merge_gate_boundaries",
]
