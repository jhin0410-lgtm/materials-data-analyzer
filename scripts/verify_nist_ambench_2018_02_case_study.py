"""Verify NIST AM-Bench 2018-02 case-study provenance and artifact bindings."""
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
CASE_MANIFEST = "ambench_case_study_manifest.json"
HANDOFF_MANIFEST = "characterization_handoff_manifest.json"
CASE_STUDY_ID = "nist_ambench_2018_02_process_characterization"
REQUIRED_OUTPUTS = {
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
            "Verify source hashes, artifact checksums, feature provenance, and "
            "handoff bindings for an existing NIST AM-Bench output directory."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Existing NIST AM-Bench case-study output directory.",
    )
    return parser.parse_args()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return value


def _as_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def _resolve(output_dir: Path, recorded: object, label: str) -> Path:
    if not isinstance(recorded, str) or not recorded.strip():
        raise ValueError(f"{label} path must be a non-empty string.")
    recorded_path = Path(recorded)
    candidates = [output_dir / recorded_path.name, recorded_path]
    if not recorded_path.is_absolute():
        candidates.insert(1, output_dir / recorded_path)
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{label} not found from recorded path: {recorded}")


def _check_sha(path: Path, expected: object, label: str) -> str:
    actual = sha256_file(path)
    if not isinstance(expected, str) or expected != actual:
        raise ValueError(
            f"{label} checksum mismatch: expected {expected}, actual {actual}."
        )
    return actual


def _resolve_case_outputs(
    output_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    outputs = _as_dict(manifest.get("outputs"), "case manifest outputs")
    checksums = _as_dict(
        manifest.get("artifact_checksums"),
        "case manifest artifact_checksums",
    )
    missing = sorted(REQUIRED_OUTPUTS - set(checksums))
    if missing:
        raise ValueError(
            "Case manifest is missing checksummed required output(s): "
            + ", ".join(missing)
        )

    resolved: dict[str, Path] = {}
    for name, expected_sha in sorted(checksums.items()):
        if name not in outputs:
            raise ValueError(f"Case manifest checksum has no output path for {name}.")
        path = _resolve(output_dir, outputs[name], f"case output {name}")
        _check_sha(path, expected_sha, f"case output {name}")
        resolved[name] = path
    return resolved


def _verify_feature_binding(long_path: Path, measurement_sha: str) -> dict[str, int]:
    table = validate_characterization_features(
        pd.read_csv(long_path),
        source_name=str(long_path),
    )
    counts = {
        "feature_record_count": int(len(table)),
        "sample_count": int(table["sample_id"].nunique()),
        "measurement_count": int(table["measurement_id"].nunique()),
    }
    if counts != {
        "feature_record_count": 40,
        "sample_count": 10,
        "measurement_count": 10,
    }:
        raise ValueError(f"Unexpected characterization feature counts: {counts!r}.")
    if not table.groupby("sample_id", sort=True).size().eq(4).all():
        raise ValueError("Each NIST trace must have exactly four feature records.")
    if table["source_file"].isna().any() or set(table["source_file"]) != {
        MEASUREMENT_SOURCE.name
    }:
        raise ValueError(
            "Characterization source_file values do not bind every feature record "
            "to the tracked NIST measurement table."
        )
    if table["source_sha256"].isna().any() or set(table["source_sha256"]) != {
        measurement_sha
    }:
        raise ValueError(
            "Characterization source_sha256 values do not bind every feature record "
            "to the tracked NIST measurement table."
        )
    return counts


def _verify_handoff(
    output_dir: Path,
    case_outputs: dict[str, Path],
) -> None:
    handoff = _read_json(output_dir / HANDOFF_MANIFEST, "handoff manifest")
    if handoff.get("schema_version") != "1.0":
        raise ValueError("Handoff manifest schema_version must be 1.0.")
    if handoff.get("workflow") != "characterization_feature_handoff":
        raise ValueError("Unexpected handoff workflow identifier.")
    if handoff.get("counts") != EXPECTED_HANDOFF_COUNTS:
        raise ValueError(f"Unexpected handoff counts: {handoff.get('counts')!r}.")
    if handoff.get("join_summary") != EXPECTED_JOIN_SUMMARY:
        raise ValueError(
            f"Unexpected handoff join summary: {handoff.get('join_summary')!r}."
        )

    sources = handoff.get("characterization_sources")
    if not isinstance(sources, list) or len(sources) != 1:
        raise ValueError("Handoff manifest must contain one characterization source.")
    feature_source = _as_dict(sources[0], "handoff characterization source")
    feature_sha = sha256_file(case_outputs["characterization_long"])
    if feature_source.get("sha256") != feature_sha:
        raise ValueError(
            "Handoff characterization source sha256 does not bind to the generated "
            "long-format feature table."
        )
    if feature_source.get("row_count") != 40:
        raise ValueError("Handoff characterization source row_count must be 40.")
    if sha256_file(
        _resolve(output_dir, feature_source.get("path"), "handoff feature source")
    ) != feature_sha:
        raise ValueError("Handoff feature source path resolves to different content.")

    process_source = _as_dict(handoff.get("process_source"), "handoff process source")
    process_sha = sha256_file(case_outputs["normalized_process_table"])
    if process_source.get("sha256") != process_sha:
        raise ValueError(
            "Handoff process source sha256 does not bind to the generated normalized "
            "process table."
        )
    if sha256_file(
        _resolve(output_dir, process_source.get("path"), "handoff process source")
    ) != process_sha:
        raise ValueError("Handoff process source path resolves to different content.")

    handoff_outputs = _as_dict(handoff.get("outputs"), "handoff outputs")
    for name in (
        "validated_long",
        "feature_dictionary",
        "wide_features",
        "integrated_table",
        "join_audit",
    ):
        nested_path = _resolve(
            output_dir,
            handoff_outputs.get(name),
            f"handoff output {name}",
        )
        if sha256_file(nested_path) != sha256_file(case_outputs[name]):
            raise ValueError(
                f"Handoff output {name} does not bind to the checksummed case output."
            )


def verify_case_study(output_dir: str | Path) -> dict[str, Any]:
    """Verify the existing case-study output without regenerating artifacts."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Case-study output directory not found: {output_dir}")

    manifest = _read_json(output_dir / CASE_MANIFEST, "case manifest")
    if manifest.get("case_study_id") != CASE_STUDY_ID:
        raise ValueError("Unexpected NIST AM-Bench case_study_id.")
    if manifest.get("counts") != EXPECTED_CASE_COUNTS:
        raise ValueError(f"Unexpected case-study counts: {manifest.get('counts')!r}.")

    source = _as_dict(manifest.get("source"), "case manifest source")
    process_sha = sha256_file(PROCESS_SOURCE)
    measurement_sha = sha256_file(MEASUREMENT_SOURCE)
    if source.get("process_source_sha256") != process_sha:
        raise ValueError("Case manifest does not bind to the tracked process source.")
    if source.get("measurement_source_sha256") != measurement_sha:
        raise ValueError("Case manifest does not bind to the tracked measurement source.")
    if source.get("network_access_performed") is not False:
        raise ValueError("Case manifest must record network_access_performed=false.")
    if source.get("raw_images_redistributed") is not False:
        raise ValueError("Case manifest must record raw_images_redistributed=false.")

    validation = _as_dict(manifest.get("validation"), "case validation")
    for key in ("row_order_join_used", "model_trained", "optimization_performed"):
        if validation.get(key) is not False:
            raise ValueError(f"Case validation must record {key}=false.")
    closeout = _as_dict(manifest.get("scientific_closeout"), "scientific closeout")
    if closeout.get("status") != "diagnostic":
        raise ValueError("Scientific closeout status must remain diagnostic.")

    case_outputs = _resolve_case_outputs(output_dir, manifest)
    feature_counts = _verify_feature_binding(
        case_outputs["characterization_long"],
        measurement_sha,
    )
    _verify_handoff(output_dir, case_outputs)

    audit = pd.read_csv(case_outputs["join_audit"])
    if list(audit.columns) != ["sample_id", "join_status"]:
        raise ValueError("Unexpected join-audit schema.")
    if len(audit) != 10 or not audit["join_status"].eq("matched").all():
        raise ValueError("Join audit must contain ten matched samples.")
    integrated = pd.read_csv(case_outputs["integrated_table"])
    if len(integrated) != 10 or integrated["sample_id"].nunique() != 10:
        raise ValueError("Integrated sample table must contain ten unique samples.")

    return {
        "status": "verified",
        "case_study_id": CASE_STUDY_ID,
        "checksummed_artifact_count": int(len(case_outputs)),
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
