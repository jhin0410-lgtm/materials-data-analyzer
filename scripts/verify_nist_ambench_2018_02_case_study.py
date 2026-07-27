"""Verify NIST AM-Bench 2018-02 case-study artifact and provenance bindings."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from loaders.characterization_features import (  # noqa: E402
    sha256_file,
    validate_characterization_features,
)

CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "nist_ambench_2018_02"
PROCESS_SOURCE = CASE_DIR / "source_process_conditions.csv"
MEASUREMENT_SOURCE = CASE_DIR / "source_melt_pool_measurements.csv"
CASE_MANIFEST_NAME = "ambench_case_study_manifest.json"
HANDOFF_MANIFEST_NAME = "characterization_handoff_manifest.json"
CASE_STUDY_ID = "nist_ambench_2018_02_process_characterization"
EXPECTED_CASE_COUNTS = {
    "trace_count": 10,
    "process_condition_count": 3,
    "characterization_record_count": 40,
    "matched_sample_count": 10,
}
EXPECTED_HANDOFF_COUNTS = {
    "feature_record_count": 40,
    "sample_count": 10,
    "measurement_count": 10,
    "feature_definition_count": 4,
    "wide_feature_count": 4,
}
EXPECTED_JOIN_SUMMARY = {
    "matched": 10,
    "process_only": 0,
    "characterization_only": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify checksums, source bindings, handoff-manifest inputs, and "
            "sample-join evidence for an existing NIST AM-Bench 2018-02 output."
        )
    )
    parser.add_argument("--output", required=True, help="Existing case-study output directory.")
    return parser.parse_args()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return value


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _resolve_recorded_path(output_dir: Path, recorded: object, label: str) -> Path:
    if not isinstance(recorded, str) or not recorded.strip():
        raise ValueError(f"{label} path must be a non-empty string.")

    recorded_path = Path(recorded)
    candidates = [output_dir / recorded_path.name]
    if not recorded_path.is_absolute():
        candidates.append(output_dir / recorded_path)
    candidates.append(recorded_path)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{label} not found from recorded path: {recorded}")


def _assert_checksum(path: Path, expected: object, label: str) -> str:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{label} expected SHA-256 is invalid.")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"{label} checksum mismatch: expected {expected}, actual {actual}."
        )
    return actual


def _verify_source_manifest(case_manifest: dict[str, Any]) -> dict[str, str]:
    source = _mapping(case_manifest.get("source"), "case manifest source")
    expected_process_sha = sha256_file(PROCESS_SOURCE)
    expected_measurement_sha = sha256_file(MEASUREMENT_SOURCE)

    if source.get("process_source_sha256") != expected_process_sha:
        raise ValueError(
            "Case manifest process_source_sha256 does not bind to the tracked "
            "NIST process source table."
        )
    if source.get("measurement_source_sha256") != expected_measurement_sha:
        raise ValueError(
            "Case manifest measurement_source_sha256 does not bind to the tracked "
            "NIST measurement source table."
        )
    if source.get("network_access_performed") is not False:
        raise ValueError("Case manifest must record network_access_performed=false.")
    if source.get("raw_images_redistributed") is not False:
        raise ValueError("Case manifest must record raw_images_redistributed=false.")

    return {
        "process_source_sha256": expected_process_sha,
        "measurement_source_sha256": expected_measurement_sha,
    }


def _verify_case_artifacts(
    output_dir: Path,
    case_manifest: dict[str, Any],
) -> dict[str, Path]:
    outputs = _mapping(case_manifest.get("outputs"), "case manifest outputs")
    checksums = _mapping(
        case_manifest.get("artifact_checksums"),
        "case manifest artifact_checksums",
    )
    if not checksums:
        raise ValueError("Case manifest artifact_checksums must not be empty.")

    resolved: dict[str, Path] = {}
    for name, expected_sha in sorted(checksums.items()):
        if name not in outputs:
            raise ValueError(f"Case manifest checksum has no output path for {name}.")
        path = _resolve_recorded_path(output_dir, outputs[name], f"case output {name}")
        _assert_checksum(path, expected_sha, f"case output {name}")
        resolved[name] = path
    return resolved


def _verify_feature_source_binding(
    long_path: Path,
    expected_measurement_sha: str,
) -> dict[str, int]:
    table = validate_characterization_features(
        pd.read_csv(long_path),
        source_name=str(long_path),
    )
    if len(table) != 40:
        raise ValueError("Characterization long table must contain exactly 40 records.")
    if table["sample_id"].nunique() != 10:
        raise ValueError("Characterization long table must contain exactly 10 samples.")
    if table["measurement_id"].nunique() != 10:
        raise ValueError("Characterization long table must contain exactly 10 measurements.")
    if not table.groupby("sample_id", sort=True).size().eq(4).all():
        raise ValueError("Each NIST trace must have exactly four characterization records.")

    source_files = set(table["source_file"].dropna().astype(str))
    if table["source_file"].isna().any() or source_files != {MEASUREMENT_SOURCE.name}:
        raise ValueError(
            "Characterization source_file values do not bind every feature record "
            "to the tracked NIST measurement table."
        )
    source_hashes = set(table["source_sha256"].dropna().astype(str))
    if table["source_sha256"].isna().any() or source_hashes != {
        expected_measurement_sha
    }:
        raise ValueError(
            "Characterization source_sha256 values do not bind every feature record "
            "to the tracked NIST measurement table."
        )

    return {
        "feature_record_count": int(len(table)),
        "sample_count": int(table["sample_id"].nunique()),
        "measurement_count": int(table["measurement_id"].nunique()),
    }


def _verify_handoff_manifest(
    output_dir: Path,
    resolved_case_outputs: dict[str, Path],
) -> None:
    handoff_path = output_dir / HANDOFF_MANIFEST_NAME
    handoff = _read_json(handoff_path, "characterization handoff manifest")
    if handoff.get("schema_version") != "1.0":
        raise ValueError("Characterization handoff manifest schema_version must be 1.0.")
    if handoff.get("workflow") != "characterization_feature_handoff":
        raise ValueError("Unexpected characterization handoff workflow identifier.")

    sources = handoff.get("characterization_sources")
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("Handoff manifest must contain exactly one characterization source.")
    characterization_source = _mapping(sources[0], "handoff characterization source")
    long_path = resolved_case_outputs["characterization_long"]
    expected_long_sha = sha256_file(long_path)
    if characterization_source.get("sha256") != expected_long_sha:
        raise ValueError(
            "Handoff characterization source sha256 does not bind to the generated "
            "characterization long table."
        )
    if characterization_source.get("row_count") != 40:
        raise ValueError("Handoff characterization source row_count must be 40.")
    resolved_handoff_long = _resolve_recorded_path(
        output_dir,
        characterization_source.get("path"),
        "handoff characterization source",
    )
    if sha256_file(resolved_handoff_long) != expected_long_sha:
        raise ValueError(
            "Handoff characterization source path does not resolve to the bound "
            "characterization long table."
        )

    process_source = _mapping(handoff.get("process_source"), "handoff process source")
    process_path = resolved_case_outputs["normalized_process_table"]
    expected_process_sha = sha256_file(process_path)
    if process_source.get("sha256") != expected_process_sha:
        raise ValueError(
            "Handoff process source sha256 does not bind to the generated normalized "
            "process table."
        )
    resolved_handoff_process = _resolve_recorded_path(
        output_dir,
        process_source.get("path"),
        "handoff process source",
    )
    if sha256_file(resolved_handoff_process) != expected_process_sha:
        raise ValueError(
            "Handoff process source path does not resolve to the bound normalized "
            "process table."
        )

    if handoff.get("counts") != EXPECTED_HANDOFF_COUNTS:
        raise ValueError(
            f"Unexpected handoff counts: {handoff.get('counts')!r}."
        )
    if handoff.get("join_summary") != EXPECTED_JOIN_SUMMARY:
        raise ValueError(
            f"Unexpected handoff join summary: {handoff.get('join_summary')!r}."
        )

    handoff_outputs = _mapping(handoff.get("outputs"), "handoff outputs")
    for name in (
        "validated_long",
        "feature_dictionary",
        "wide_features",
        "integrated_table",
        "join_audit",
    ):
        if name not in resolved_case_outputs:
            raise ValueError(f"Case manifest does not checksum handoff output {name}.")
        if name not in handoff_outputs:
            raise ValueError(f"Handoff manifest does not record output {name}.")
        nested_path = _resolve_recorded_path(
            output_dir,
            handoff_outputs[name],
            f"handoff output {name}",
        )
        if sha256_file(nested_path) != sha256_file(resolved_case_outputs[name]):
            raise ValueError(
                f"Handoff output {name} does not bind to the checksummed case output."
            )


def _verify_counts_and_join(
    case_manifest: dict[str, Any],
    resolved_case_outputs: dict[str, Path],
) -> None:
    if case_manifest.get("case_study_id") != CASE_STUDY_ID:
        raise ValueError("Unexpected NIST AM-Bench case_study_id.")
    if case_manifest.get("counts") != EXPECTED_CASE_COUNTS:
        raise ValueError(f"Unexpected case-study counts: {case_manifest.get('counts')!r}.")

    validation = _mapping(case_manifest.get("validation"), "case validation")
    if validation.get("row_order_join_used") is not False:
        raise ValueError("Case validation must record row_order_join_used=false.")
    if validation.get("model_trained") is not False:
        raise ValueError("Case validation must record model_trained=false.")
    if validation.get("optimization_performed") is not False:
        raise ValueError("Case validation must record optimization_performed=false.")

    audit = pd.read_csv(resolved_case_outputs["join_audit"])
    if list(audit.columns) != ["sample_id", "join_status"]:
        raise ValueError("Join audit schema is not the expected two-column contract.")
    if len(audit) != 10 or not audit["join_status"].eq("matched").all():
        raise ValueError("Join audit must contain ten matched samples and no unmatched rows.")

    integrated = pd.read_csv(resolved_case_outputs["integrated_table"])
    if len(integrated) != 10 or integrated["sample_id"].nunique() != 10:
        raise ValueError("Integrated sample table must contain ten unique samples.")


def verify_case_study(output_dir: str | Path) -> dict[str, Any]:
    """Verify source, artifact, feature-record, and handoff-manifest bindings."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Case-study output directory not found: {output_dir}")

    case_manifest = _read_json(
        output_dir / CASE_MANIFEST_NAME,
        "NIST AM-Bench case manifest",
    )
    source_hashes = _verify_source_manifest(case_manifest)
    resolved_outputs = _verify_case_artifacts(output_dir, case_manifest)

    required_outputs = {
        "normalized_process_table",
        "characterization_long",
        "validated_long",
        "feature_dictionary",
        "wide_features",
        "integrated_table",
        "join_audit",
        "case_summary",
        "width_plot",
        "depth_plot",
        "report",
    }
    missing = sorted(required_outputs - set(resolved_outputs))
    if missing:
        raise ValueError(
            "Case manifest is missing checksummed required output(s): "
            + ", ".join(missing)
        )

    feature_counts = _verify_feature_source_binding(
        resolved_outputs["characterization_long"],
        source_hashes["measurement_source_sha256"],
    )
    _verify_handoff_manifest(output_dir, resolved_outputs)
    _verify_counts_and_join(case_manifest, resolved_outputs)

    closeout = _mapping(case_manifest.get("scientific_closeout"), "scientific closeout")
    if closeout.get("status") != "diagnostic":
        raise ValueError("Scientific closeout status must remain diagnostic.")

    return {
        "status": "verified",
        "case_study_id": CASE_STUDY_ID,
        "checksummed_artifact_count": int(len(resolved_outputs)),
        **feature_counts,
        "matched_sample_count": 10,
        "scientific_status": "diagnostic",
    }


def main() -> None:
    args = parse_args()
    try:
        result = verify_case_study(args.output)
    except (OSError, ValueError, TypeError, KeyError, pd.errors.EmptyDataError) as exc:
        print(f"NIST AM-Bench integrity verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("NIST AM-Bench 2018-02 integrity verification passed.")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
