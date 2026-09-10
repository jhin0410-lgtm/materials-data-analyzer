"""Independent source-byte replay hardening for autonomous-production merge gates.

Persisted self-hashes authenticate internal consistency, not scientific provenance.  This
layer therefore rebuilds the bounded scientific artifacts from the exact source bytes that
survived acquisition and rejects any persisted result that cannot be reproduced by the
canonical producer.  It also replays the canonical acquisition-record binder and explicitly
checks the late-cycle authority boundary.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from .acquisition_record_binding import (
    AcquisitionRecordBindingError,
    authenticate_acquisition_record_binding,
)
from .in625_tensile_reviewed_intake_v2 import (
    In625TensileReviewedIntakeV2Error,
    build_reviewed_in625_tensile_intake_v2,
)
from .nist_mds2_2923_network_policy import (
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    PRODUCT_ID as NIST_PRODUCT_ID,
)
from .nist_mds2_2923_scientific_intake import (
    NistMds22923ScientificIntakeError,
    audit_mds2_2923,
)

_REVIEWED_TENSILE_POLICY = (
    "configs/research/in625_tensile_reviewed_intake.v1.json"
)
_REVIEWED_TENSILE_MANIFEST = "reviewed-tensile/reviewed_tensile_manifest.v2.json"
_REVIEWED_TENSILE_ROWS = "reviewed-tensile/reviewed_tensile_rows.v2.jsonl"
_SELECTED_SOURCE_ROOT = "selected-source-files"

_DENIED_TRUE_AUTHORITY_FIELDS = {
    "automatic_execution_authorized",
    "automatic_scientific_promotion",
    "bridge_established",
    "causal_authority_established",
    "causal_authority_granted",
    "causal_inference_authorized",
    "causal_inference_eligible_from_this_audit",
    "candidate_urls_gain_acquisition_authority",
    "direct_nist_condition_comparability_established",
    "direct_numerical_cross_source_validation_authorized",
    "direct_numerical_validation_authorized",
    "direct_target_condition_comparability_established",
    "empirical_model_validation_established",
    "geometry_condition_mapping_established",
    "hypothesis_truth_established",
    "numerical_cross_source_validation_authorized",
    "optimization_authority_established",
    "optimization_authority_granted",
    "optimization_authorized",
    "optimization_eligible_from_this_audit",
    "paper_claims_promoted_to_row_level_authority",
    "paper_evidence_promoted_to_row_level_authority",
    "positive_scientific_closeout",
    "positive_scientific_closeout_established",
    "scientific_status_changed",
    "scientific_support_established",
}
_ZERO_AUTHORITY_FIELDS = {
    "directly_comparable_mds2_rows",
    "issue_76_exact_target_cells_satisfied",
}


class AutonomousProductionSourceReplayHardeningError(ValueError):
    """Raised when persisted autonomous evidence cannot be replayed from source bytes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionSourceReplayHardeningError(message)


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


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionSourceReplayHardeningError(
            f"{label} must be valid persisted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{label} root must be an object")
    return value


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _inside(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionSourceReplayHardeningError(
            f"{label} escaped its authenticated root"
        ) from exc


def _semantic_tensile_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in (
        "manifest_sha256",
        "policy",
        "workbook",
        "documentation",
        "row_artifact",
    ):
        result.pop(key, None)
    return result


def _validate_row_record(
    record: object,
    raw: bytes,
    *,
    label: str,
) -> Mapping[str, Any]:
    row = _mapping(record, label=label)
    _require(
        row.get("sha256") == hashlib.sha256(raw).hexdigest()
        and row.get("bytes") == len(raw)
        and row.get("row_count") == len(raw.splitlines()),
        f"{label} digest/count does not match its exact JSONL bytes",
    )
    return row


def _require_tensile_replay_match(
    *,
    persisted_manifest: Mapping[str, Any],
    persisted_row_bytes: bytes,
    replay_manifest: Mapping[str, Any],
    replay_row_bytes: bytes,
) -> None:
    persisted_row = _validate_row_record(
        persisted_manifest.get("row_artifact"),
        persisted_row_bytes,
        label="persisted reviewed tensile row artifact",
    )
    replay_row = _validate_row_record(
        replay_manifest.get("row_artifact"),
        replay_row_bytes,
        label="replayed reviewed tensile row artifact",
    )
    _require(
        persisted_row_bytes == replay_row_bytes
        and persisted_row.get("sha256") == replay_row.get("sha256")
        and persisted_row.get("bytes") == replay_row.get("bytes")
        and persisted_row.get("row_count") == replay_row.get("row_count"),
        "reviewed tensile row artifact does not match canonical source-byte replay",
    )
    _require(
        _semantic_tensile_projection(persisted_manifest)
        == _semantic_tensile_projection(replay_manifest),
        "reviewed tensile semantic manifest does not match canonical source-byte replay",
    )


def _verify_reviewed_tensile_source_replay(root: Path) -> None:
    # The legacy raw-archive verifier already authenticates the full archive when it remains.
    # The source replay is required for the normal producer lifecycle after Dataset.zip cleanup.
    if (root / "Dataset.zip").exists():
        return

    persisted_manifest_path = root / _REVIEWED_TENSILE_MANIFEST
    persisted_rows_path = root / _REVIEWED_TENSILE_ROWS
    _require(
        persisted_manifest_path.is_file() and persisted_rows_path.is_file(),
        "post-cleanup reviewed tensile evidence is incomplete",
    )

    repository_root = _merge_gate._trusted_repository_root().resolve(strict=True)
    policy_path = (repository_root / _REVIEWED_TENSILE_POLICY).resolve(strict=True)
    _inside(policy_path, repository_root, label="reviewed tensile policy")
    policy = _load_json(policy_path, label="reviewed tensile policy")

    def selected_source(record_name: str) -> Path:
        record = _mapping(policy.get(record_name), label=f"reviewed tensile policy {record_name}")
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
        path = (root / _SELECTED_SOURCE_ROOT / Path(*member_path.parts)).resolve(
            strict=True
        )
        _inside(path, root, label=f"reviewed tensile {record_name}")
        raw = path.read_bytes()
        _require(
            record.get("sha256") == hashlib.sha256(raw).hexdigest()
            and record.get("size_bytes") == len(raw),
            f"reviewed tensile {record_name} source bytes drifted from tracked policy",
        )
        return path

    workbook_path = selected_source("workbook")
    readme_path = selected_source("documentation")
    persisted_manifest = _load_json(
        persisted_manifest_path,
        label="persisted reviewed tensile manifest",
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
        raise AutonomousProductionSourceReplayHardeningError(
            "reviewed tensile canonical source replay failed"
        ) from exc

    _require_tensile_replay_match(
        persisted_manifest=persisted_manifest,
        persisted_row_bytes=persisted_row_bytes,
        replay_manifest=replay_manifest,
        replay_row_bytes=replay_row_bytes,
    )


def _authenticate_nist_package(
    *,
    root: Path,
    path: str,
    rule: Mapping[str, Any],
    package_index: int,
    top_receipt: Mapping[str, Any],
    expected_metadata_sha256: str = EXPECTED_METADATA_SHA256,
) -> tuple[bytes, bytes]:
    nist_root = (root / "nist-mds2-2923").resolve(strict=True)
    package = (nist_root / f"artifact-{package_index:02d}").resolve(strict=True)
    artifact = (package / path).resolve(strict=True)
    _inside(package, nist_root, label=f"NIST package {package_index}")
    _inside(artifact, package, label=f"NIST artifact {path}")
    raw = artifact.read_bytes()
    _require(
        len(raw) == rule.get("size_bytes")
        and hashlib.sha256(raw).hexdigest() == rule.get("sha256"),
        f"NIST exact artifact bytes drifted before canonical binding replay: {path}",
    )

    manifest_path = package / "acquisition_manifest.json"
    declaration_path = package / "acquisition_declaration.json"
    metadata_path = package / "source_metadata.json"
    _require(
        manifest_path.is_file()
        and declaration_path.is_file()
        and metadata_path.is_file(),
        f"NIST package provenance files missing for canonical replay: {path}",
    )
    manifest_bytes = manifest_path.read_bytes()
    declaration_bytes = declaration_path.read_bytes()
    metadata_bytes = metadata_path.read_bytes()
    _require(
        hashlib.sha256(metadata_bytes).hexdigest() == expected_metadata_sha256,
        f"NIST package metadata bytes drifted before canonical replay: {path}",
    )

    try:
        authenticated = authenticate_acquisition_record_binding(
            evidence_bytes=raw,
            acquisition_manifest_bytes=manifest_bytes,
            acquisition_declaration_bytes=declaration_bytes,
        )
    except AcquisitionRecordBindingError as exc:
        raise AutonomousProductionSourceReplayHardeningError(
            f"NIST canonical acquisition-record binding failed: {path}"
        ) from exc

    _require(
        authenticated.get("recorded_acquisition_provenance_authenticated") is True
        and authenticated.get("evidence_artifact_sha256") == rule.get("sha256")
        and authenticated.get("acquisition_manifest_sha256")
        == top_receipt.get("acquisition_manifest_sha256")
        and authenticated.get("acquisition_declaration_sha256")
        == top_receipt.get("acquisition_declaration_sha256")
        and hashlib.sha256(manifest_bytes).hexdigest()
        == top_receipt.get("acquisition_manifest_sha256")
        and hashlib.sha256(declaration_bytes).hexdigest()
        == top_receipt.get("acquisition_declaration_sha256"),
        f"NIST canonical acquisition-record binding disagrees with persisted receipt: {path}",
    )
    return raw, metadata_bytes


def _require_nist_intake_replay_match(
    *, persisted: Mapping[str, Any], replayed: Mapping[str, Any]
) -> None:
    _require(
        dict(persisted) == dict(replayed),
        "NIST scientific intake does not match canonical source-byte replay",
    )


def _verify_successful_nist_source_replay(root: Path) -> None:
    aggregate_path = root / "nist-network-acquisition-receipt.json"
    if not aggregate_path.is_file():
        return
    aggregate = _load_json(aggregate_path, label="NIST successful acquisition receipt")
    if aggregate.get("acquisition_status") != "exact_nist_mds2_2923_source_files_acquired":
        return

    receipts = aggregate.get("receipts")
    _require(
        isinstance(receipts, list) and len(receipts) == len(EXPECTED_FILES),
        "NIST successful acquisition receipt does not expose the exact per-file receipt set",
    )
    source_bytes: dict[str, bytes] = {}
    metadata_bytes: bytes | None = None
    for index, (path, rule) in enumerate(EXPECTED_FILES.items(), start=1):
        top = receipts[index - 1]
        _require(isinstance(top, Mapping), f"NIST per-file receipt {index} is invalid")
        _require(
            top.get("candidate_id") == f"nist-pdr:{NIST_PRODUCT_ID}:{path}"
            and top.get("artifact_path") == path
            and top.get("artifact_sha256") == rule.get("sha256")
            and top.get("artifact_size_bytes") == rule.get("size_bytes"),
            f"NIST per-file receipt identity drifted before canonical replay: {path}",
        )
        raw, package_metadata = _authenticate_nist_package(
            root=root,
            path=path,
            rule=rule,
            package_index=index,
            top_receipt=top,
        )
        source_bytes[path] = raw
        if metadata_bytes is None:
            metadata_bytes = package_metadata
        else:
            _require(
                metadata_bytes == package_metadata,
                "NIST successful packages disagree on exact authenticated metadata bytes",
            )

    _require(metadata_bytes is not None, "NIST canonical replay omitted source metadata bytes")
    try:
        replayed = audit_mds2_2923(
            workbook_bytes=source_bytes["Master_TrackList_Measurements.xlsx"],
            readme_bytes=source_bytes["2923_README.txt"],
            nerdm_metadata_bytes=metadata_bytes,
        )
    except NistMds22923ScientificIntakeError as exc:
        raise AutonomousProductionSourceReplayHardeningError(
            "NIST scientific intake canonical source-byte replay failed"
        ) from exc
    persisted = _load_json(
        root / "nist-scientific-intake.json",
        label="persisted NIST scientific intake",
    )
    _require_nist_intake_replay_match(persisted=persisted, replayed=replayed)


def _verify_cycle_chain(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    digest = manifest.get("manifest_sha256")
    _require(isinstance(digest, str), "autonomous manifest self-hash is missing")
    unsigned_manifest = dict(manifest)
    unsigned_manifest.pop("manifest_sha256", None)
    _require(
        _canonical_sha(unsigned_manifest) == digest,
        "autonomous manifest self-hash mismatch during late-cycle replay",
    )
    raw_cycles = manifest.get("cycles")
    _require(isinstance(raw_cycles, list) and raw_cycles, "autonomous cycle chain is invalid")
    cycles: list[dict[str, Any]] = []
    predecessor: str | None = None
    for expected_index, raw_cycle in enumerate(raw_cycles, start=1):
        _require(isinstance(raw_cycle, dict), f"cycle {expected_index} must be an object")
        cycle = dict(raw_cycle)
        cycle_sha = cycle.get("cycle_sha256")
        _require(isinstance(cycle_sha, str), f"cycle {expected_index} self-hash is missing")
        unsigned = dict(cycle)
        unsigned.pop("cycle_sha256", None)
        _require(
            _canonical_sha(unsigned) == cycle_sha,
            f"cycle {expected_index} self-hash mismatch during late-cycle replay",
        )
        _require(
            cycle.get("cycle_index") == expected_index,
            f"cycle {expected_index} index drifted during late-cycle replay",
        )
        if predecessor is not None:
            _require(
                cycle.get("predecessor_cycle_sha256") == predecessor,
                f"cycle {expected_index} predecessor binding mismatch during late-cycle replay",
            )
        predecessor = cycle_sha
        cycles.append(cycle)
    return cycles


def _scan_authority(value: object, *, cycle_index: int, path: str = "cycle") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in _DENIED_TRUE_AUTHORITY_FIELDS:
                _require(
                    child is False,
                    f"cycle {cycle_index} attempted unsupported authority promotion at {child_path}",
                )
            if key in _ZERO_AUTHORITY_FIELDS:
                _require(
                    child == 0 and not isinstance(child, bool),
                    f"cycle {cycle_index} attempted unsupported quantitative authority at {child_path}",
                )
            _scan_authority(child, cycle_index=cycle_index, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_authority(
                child,
                cycle_index=cycle_index,
                path=f"{path}[{index}]",
            )


def _verify_late_cycle_authority_boundaries(cycles: list[dict[str, Any]]) -> None:
    for cycle in cycles[3:8]:
        cycle_index = int(cycle["cycle_index"])
        _scan_authority(cycle, cycle_index=cycle_index)
        if cycle_index == 4:
            _require(
                cycle.get("directly_comparable_mds2_rows") == 0
                and cycle.get("paper_claims_promoted_to_row_level_authority") is False
                and cycle.get("direct_numerical_validation_authorized") is False
                and cycle.get("issue_76_exact_target_cells_satisfied") == 0,
                "cycle 4 geometry mapping authority boundary drifted",
            )
        elif cycle_index == 6:
            _require(
                cycle.get("bridge_established") is False
                and cycle.get("directly_comparable_mds2_rows") == 0
                and cycle.get("issue_76_exact_target_cells_satisfied") == 0,
                "cycle 6 bridge authority boundary drifted",
            )
        elif cycle_index == 8:
            _require(
                cycle.get("candidate_links_followed") == 0
                and cycle.get("candidate_urls_gain_acquisition_authority") is False,
                "cycle 8 source-discovery acquisition authority drifted",
            )


def verify_source_replay_boundaries(output_root: str | Path) -> None:
    """Replay source-derived evidence and late-cycle authority from persisted exact bytes."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load_json(
        root / "autonomous-production-manifest.json",
        label="autonomous production manifest",
    )
    cycles = _verify_cycle_chain(manifest)
    _verify_late_cycle_authority_boundaries(cycles)
    _verify_reviewed_tensile_source_replay(root)
    _verify_successful_nist_source_replay(root)


__all__ = [
    "AutonomousProductionSourceReplayHardeningError",
    "verify_source_replay_boundaries",
]
