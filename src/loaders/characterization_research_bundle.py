"""Research-grade characterization bundle intake for schema 1.0 and 1.1.

The historical feature consumer remains the compatibility engine for schema 1.0.  Schema
1.1 adds a scientific-evidence-ladder object that older closed-world consumers correctly
reject.  This adapter independently validates that extension, validates the unchanged base
bundle through an isolated schema-1.0 compatibility copy, and then records the verified
maturity state in consumer outputs.

No producer Python package is imported.  The compatibility copy is validation plumbing,
not a schema downgrade of the authoritative input and not scientific evidence.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

from .characterization_bundle import (
    BUNDLE_SCHEMA_VERSION,
    BUNDLE_TYPE,
    MANIFEST_NAME,
    REPORT_NAME,
    SUMMARY_NAME,
    ValidatedCharacterizationBundle,
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from .characterization_evidence_ladder import (
    CharacterizationEvidenceLadderError,
    validate_scientific_evidence_ladder_record,
)
from .characterization_features import sha256_file

EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION = "1.1"
SUPPORTED_BUNDLE_SCHEMA_VERSIONS = {
    BUNDLE_SCHEMA_VERSION,
    EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION,
}


@dataclass(frozen=True)
class ValidatedResearchCharacterizationBundle:
    """Base characterization bundle plus independently replayed maturity state."""

    manifest_path: Path
    manifest: dict[str, Any]
    feature_path: Path
    sample_context_path: Path
    evidence_paths: dict[str, Path]
    feature_table: pd.DataFrame
    sample_context: pd.DataFrame
    evidence_identity_binding: dict[str, Any]
    scientific_evidence_ladder: dict[str, Any] | None
    scientific_evidence_ladder_path: Path | None
    scientific_evidence_ladder_assessment: dict[str, Any] | None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in characterization research bundle: {key}")
        result[key] = value
    return result


def _read_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path)
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError(
            f"characterization bundle manifest not found or unsafe: {manifest_path}"
        )
    try:
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"could not read characterization research bundle: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("characterization research bundle manifest root must be an object")
    return manifest_path.resolve(), payload


def _record_path(root: Path, record: object, label: str) -> Path:
    if not isinstance(record, dict):
        raise ValueError(f"{label} must be an object")
    name = record.get("path")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label}.path must be a non-empty string")
    relative = Path(name)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != name:
        raise ValueError(f"{label}.path must be one direct sibling filename")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"{label} is missing or unsafe: {path}")
    expected_sha = record.get("sha256")
    expected_size = record.get("size_bytes")
    actual_sha = sha256_file(path)
    if not isinstance(expected_sha, str) or expected_sha != actual_sha:
        raise ValueError(f"{label} checksum mismatch")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        raise ValueError(f"{label}.size_bytes must be an integer")
    if expected_size != path.stat().st_size:
        raise ValueError(f"{label} size_bytes mismatch")
    return path


def _authoritative_base_paths(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> tuple[Path, Path, dict[str, Path]]:
    root = manifest_path.parent
    feature = _record_path(root, manifest.get("feature_table"), "feature_table")
    context = _record_path(root, manifest.get("sample_context"), "sample_context")
    evidence = manifest.get("evidence_references")
    if not isinstance(evidence, dict) or set(evidence) != {
        "source_manifest",
        "analysis_manifest",
        "comparability_matrix",
    }:
        raise ValueError(
            "evidence_references must contain source_manifest, analysis_manifest, and comparability_matrix exactly"
        )
    paths = {
        name: _record_path(root, record, f"evidence_references.{name}")
        for name, record in evidence.items()
    }
    return feature, context, paths


def _write_legacy_compatibility_copy(
    directory: Path,
    *,
    manifest: dict[str, Any],
    feature_path: Path,
    sample_context_path: Path,
    evidence_paths: dict[str, Path],
) -> Path:
    """Create an isolated base-schema view solely to reuse historical validation."""
    sources = [feature_path, sample_context_path, *evidence_paths.values()]
    if len({path.name for path in sources}) != len(sources):
        raise ValueError("characterization bundle base artifacts must have unique sibling names")
    for source in sources:
        shutil.copyfile(source, directory / source.name)

    compatibility_manifest = dict(manifest)
    compatibility_manifest["schema_version"] = BUNDLE_SCHEMA_VERSION
    compatibility_manifest.pop("scientific_evidence_ladder", None)
    path = directory / "characterization_handoff_bundle.compatibility.json"
    path.write_text(
        json.dumps(
            compatibility_manifest,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _from_base(
    base: ValidatedCharacterizationBundle,
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    feature_path: Path,
    sample_context_path: Path,
    evidence_paths: dict[str, Path],
    ladder: dict[str, Any] | None,
    ladder_path: Path | None,
    ladder_assessment: dict[str, Any] | None,
) -> ValidatedResearchCharacterizationBundle:
    return ValidatedResearchCharacterizationBundle(
        manifest_path=manifest_path,
        manifest=manifest,
        feature_path=feature_path,
        sample_context_path=sample_context_path,
        evidence_paths=evidence_paths,
        feature_table=base.feature_table.copy(),
        sample_context=base.sample_context.copy(),
        evidence_identity_binding=dict(base.evidence_identity_binding),
        scientific_evidence_ladder=ladder,
        scientific_evidence_ladder_path=ladder_path,
        scientific_evidence_ladder_assessment=ladder_assessment,
    )


def validate_characterization_research_bundle(
    manifest_path: str | Path,
) -> ValidatedResearchCharacterizationBundle:
    """Validate legacy schema 1.0 or independently replay schema 1.1 maturity state."""
    authoritative_path, manifest = _read_manifest(manifest_path)
    schema = manifest.get("schema_version")
    if schema not in SUPPORTED_BUNDLE_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported characterization bundle schema_version: {schema}")
    if manifest.get("bundle_type") != BUNDLE_TYPE:
        raise ValueError(
            f"Unsupported characterization bundle_type: {manifest.get('bundle_type')}"
        )
    ladder_present = "scientific_evidence_ladder" in manifest
    if ladder_present and schema != EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION:
        raise ValueError("scientific_evidence_ladder requires bundle schema_version 1.1")
    if not ladder_present and schema != BUNDLE_SCHEMA_VERSION:
        raise ValueError("bundle schema_version 1.1 requires scientific_evidence_ladder")

    feature_path, sample_context_path, evidence_paths = _authoritative_base_paths(
        authoritative_path, manifest
    )
    if schema == BUNDLE_SCHEMA_VERSION:
        base = validate_characterization_bundle(authoritative_path)
        return _from_base(
            base,
            manifest_path=authoritative_path,
            manifest=manifest,
            feature_path=feature_path,
            sample_context_path=sample_context_path,
            evidence_paths=evidence_paths,
            ladder=None,
            ladder_path=None,
            ladder_assessment=None,
        )

    with TemporaryDirectory(prefix="mda-characterization-base-validation-") as temporary:
        compatibility_path = _write_legacy_compatibility_copy(
            Path(temporary),
            manifest=manifest,
            feature_path=feature_path,
            sample_context_path=sample_context_path,
            evidence_paths=evidence_paths,
        )
        base = validate_characterization_bundle(compatibility_path)

    evidence_records = manifest.get("evidence_references")
    assert isinstance(evidence_records, dict)
    case_id = manifest.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("characterization bundle case_id is required")
    instruments = sorted(set(base.feature_table["instrument"].astype(str)))
    try:
        ladder, ladder_path, assessment = validate_scientific_evidence_ladder_record(
            bundle_root=authoritative_path.parent,
            value=manifest.get("scientific_evidence_ladder"),
            case_id=case_id,
            evidence_references=evidence_records,
            instruments=instruments,
        )
    except CharacterizationEvidenceLadderError as exc:
        raise ValueError(f"invalid scientific_evidence_ladder: {exc}") from exc

    # Detect source mutation after the compatibility copy was validated.
    if sha256_file(feature_path) != manifest["feature_table"]["sha256"]:
        raise ValueError("feature table changed during characterization research validation")
    if sha256_file(sample_context_path) != manifest["sample_context"]["sha256"]:
        raise ValueError("sample context changed during characterization research validation")
    for name, path in evidence_paths.items():
        if sha256_file(path) != evidence_records[name]["sha256"]:
            raise ValueError(
                f"evidence reference changed during characterization research validation: {name}"
            )

    return _from_base(
        base,
        manifest_path=authoritative_path,
        manifest=manifest,
        feature_path=feature_path,
        sample_context_path=sample_context_path,
        evidence_paths=evidence_paths,
        ladder=ladder,
        ladder_path=ladder_path,
        ladder_assessment=assessment,
    )


def _append_ladder_report(report_path: Path, bundle: ValidatedResearchCharacterizationBundle) -> None:
    record = bundle.scientific_evidence_ladder
    if record is None:
        return
    report = report_path.read_text(encoding="utf-8").rstrip()
    report += f"""

## Scientific Evidence Maturity (L0-L8)

- Independently replayed: `true`
- Assessment SHA-256: `{record['assessment_sha256']}`
- Declaration SHA-256: `{record['declaration_sha256']}`
- Highest contiguous supported level: `{record['highest_contiguous_supported_level']}`
- First blocking level: `{record['first_blocking_level']}`
- Scientific status promoted: `false`
- Downstream use authorized by ladder: `false`

This section records independently verified evidence maturity only. The ladder is
not new empirical evidence and cannot override the separate downstream-use policy.
"""
    report_path.write_text(report + "\n", encoding="utf-8")


def _patch_research_outputs(
    outputs: dict[str, Path],
    bundle: ValidatedResearchCharacterizationBundle,
) -> dict[str, Path]:
    if bundle.scientific_evidence_ladder is None:
        return outputs
    summary_path = outputs["cross_repository_summary"]
    report_path = outputs["cross_repository_report"]
    manifest_output = outputs["cross_repository_manifest"]
    record = bundle.scientific_evidence_ladder
    assessment = bundle.scientific_evidence_ladder_assessment
    assert assessment is not None

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["producer_bundle"] = {
        "filename": bundle.manifest_path.name,
        "sha256": sha256_file(bundle.manifest_path),
        "schema_version": bundle.manifest["schema_version"],
        "bundle_type": bundle.manifest["bundle_type"],
    }
    summary["scientific_evidence_ladder"] = {
        "independently_replayed": True,
        "declaration_sha256": record["declaration_sha256"],
        "assessment_sha256": record["assessment_sha256"],
        "subject": record["subject"],
        "highest_contiguous_supported_level": record[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": record["first_blocking_level"],
        "readiness": record["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }
    summary["software_validation"][
        "scientific_evidence_ladder_independently_replayed"
    ] = True
    summary["software_validation"]["scientific_status_promoted_by_ladder"] = False
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _append_ladder_report(report_path, bundle)

    consumer_manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    consumer_manifest["input_bundle"]["filename"] = bundle.manifest_path.name
    consumer_manifest["input_bundle"]["sha256"] = sha256_file(bundle.manifest_path)
    consumer_manifest["input_bundle"]["schema_version"] = bundle.manifest[
        "schema_version"
    ]
    consumer_manifest["scientific_evidence_ladder"] = summary[
        "scientific_evidence_ladder"
    ]
    consumer_manifest["validation"] = summary["software_validation"]
    manifest_outputs = consumer_manifest.get("outputs")
    if not isinstance(manifest_outputs, dict):
        raise ValueError("cross-repository manifest outputs must be an object")
    output_root = summary_path.parent
    consumer_manifest["output_sha256"] = {
        name: sha256_file(output_root / filename)
        for name, filename in manifest_outputs.items()
    }
    manifest_output.write_text(
        json.dumps(
            consumer_manifest,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return outputs


def consume_characterization_research_bundle(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    process_table_path: str | Path | None = None,
) -> dict[str, Path]:
    """Consume schema 1.0/1.1 while preserving the authoritative 1.1 maturity state."""
    bundle = validate_characterization_research_bundle(manifest_path)
    if bundle.manifest["schema_version"] == BUNDLE_SCHEMA_VERSION:
        return consume_characterization_bundle(
            bundle.manifest_path,
            output_dir,
            process_table_path=process_table_path,
        )

    with TemporaryDirectory(prefix="mda-characterization-base-consumption-") as temporary:
        compatibility_path = _write_legacy_compatibility_copy(
            Path(temporary),
            manifest=bundle.manifest,
            feature_path=bundle.feature_path,
            sample_context_path=bundle.sample_context_path,
            evidence_paths=bundle.evidence_paths,
        )
        outputs = consume_characterization_bundle(
            compatibility_path,
            output_dir,
            process_table_path=process_table_path,
        )
    return _patch_research_outputs(outputs, bundle)


__all__ = [
    "EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION",
    "SUPPORTED_BUNDLE_SCHEMA_VERSIONS",
    "ValidatedResearchCharacterizationBundle",
    "consume_characterization_research_bundle",
    "validate_characterization_research_bundle",
]
