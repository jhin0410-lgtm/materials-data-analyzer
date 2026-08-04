#!/usr/bin/env python3
"""Prepare a self-contained, path-redacted NASA PCoE audit staging directory."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from platform_core.battery_intelligence.common import (  # noqa: E402
    BatteryIntelligenceConfig,
    canonical_json,
    file_sha256,
)
from platform_core.battery_intelligence.nasa_audit_diagnostics import (  # noqa: E402
    augment_audit_diagnostics,
)
from platform_core.battery_intelligence.nasa_review_disposition import (  # noqa: E402
    finalize_nasa_review_disposition,
)
from platform_core.runtime_provenance import runtime_environment  # noqa: E402

WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\r\n\"']+")
POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users|mnt|tmp|var|opt)/[^\r\n\"']+")
TEXT_SUFFIXES = {".json", ".csv", ".md", ".txt", ".yaml", ".yml"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-output", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--import-output", type=Path)
    parser.add_argument("--raw-directory", type=Path)
    parser.add_argument("--disposition-input", type=Path)
    return parser.parse_args()


def _json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON object required: {path}")
    return loaded


def _infer_import_output(manifest: dict[str, Any]) -> Path | None:
    source = manifest.get("cycle_summary_source")
    if isinstance(source, dict) and source.get("path"):
        candidate = Path(str(source["path"])).expanduser()
        return candidate.parent
    return None


def _copy_tree(source: Path, destination: Path) -> list[str]:
    if not source.is_dir():
        return []
    copied: list[str] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(relative.as_posix())
    return copied


def _copy_source_evidence(raw_directory: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    for name in ("5_Battery_Data_Set.zip", "retrieval_receipt.json"):
        source = raw_directory / name
        if not source.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(name)
    return copied


def _redaction_roots(
    analysis_output: Path,
    import_output: Path | None,
    raw_directory: Path | None,
) -> dict[str, str]:
    roots = {
        str(analysis_output.resolve()): "${ANALYSIS_OUTPUT}",
        str(REPOSITORY_ROOT.resolve()): "${REPOSITORY_ROOT}",
    }
    if import_output is not None:
        roots[str(import_output.resolve())] = "${IMPORT_OUTPUT}"
    if raw_directory is not None:
        roots[str(raw_directory.resolve())] = "${RAW_DIRECTORY}"
    return dict(sorted(roots.items(), key=lambda item: len(item[0]), reverse=True))


def _portable_path_replacement(match: re.Match[str]) -> str:
    value = match.group(0).rstrip(" ,;)]}")
    basename = re.split(r"[\\/]+", value)[-1]
    suffix = f"/{basename}" if basename and "." in basename else ""
    return "${REDACTED_ABSOLUTE_PATH}" + suffix


def _redact_text(text: str, roots: dict[str, str]) -> str:
    result = text
    for root, token in roots.items():
        variants = {root, root.replace("\\", "/"), root.replace("/", "\\")}
        escaped_variants = variants | {variant.replace("\\", "\\\\") for variant in variants}
        for variant in sorted(escaped_variants, key=len, reverse=True):
            result = result.replace(variant, token)
    result = WINDOWS_ABSOLUTE_PATH.sub(_portable_path_replacement, result)
    result = POSIX_ABSOLUTE_PATH.sub(_portable_path_replacement, result)
    return result


def _redact_staged_text(root: Path, redaction_roots: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        original = path.read_text(encoding="utf-8-sig")
        redacted = _redact_text(original, redaction_roots)
        if redacted != original:
            path.write_text(redacted, encoding="utf-8", newline="\n")
            changed.append(path.relative_to(root).as_posix())
    return changed


def _remaining_absolute_paths(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for pattern in (WINDOWS_ABSOLUTE_PATH, POSIX_ABSOLUTE_PATH):
            for match in pattern.finditer(text):
                value = match.group(0).rstrip(" ,;)]}")
                if value.startswith("/${") or value.startswith("${"):
                    continue
                findings.append(
                    {
                        "relative_path": path.relative_to(root).as_posix(),
                        "matched_path": value[:300],
                    }
                )
    return findings


def _install_disposition(staging: Path, disposition_input: Path | None) -> dict[str, Any]:
    if disposition_input is None:
        return {"status": "not_supplied", "review_complete": False}
    if not disposition_input.is_file():
        raise FileNotFoundError(f"disposition input not found: {disposition_input}")
    result = finalize_nasa_review_disposition(
        analysis_output=staging,
        disposition_input=disposition_input,
    )
    summary = dict(result["summary"])
    if int(summary.get("battery_count", 0)) != 34:
        raise ValueError("completed NASA disposition must cover exactly 34 batteries")
    if summary.get("disposition_status") != "complete":
        raise ValueError("completed NASA disposition still contains pending reviews")
    return {
        "status": "completed",
        "review_complete": True,
        "battery_count": 34,
        "source_sha256": file_sha256(disposition_input),
        "output": "tables/nasa_protocol_review_disposition_final.csv",
        "predictive_evidence_level": summary.get("predictive_evidence_level"),
        "scientific_claim_changed": bool(summary.get("scientific_claim_changed")),
        "battery_removal_authorized": bool(summary.get("battery_removal_authorized")),
        "data_repair_authorized": bool(summary.get("data_repair_authorized")),
        "causal_attribution_established": bool(
            summary.get("causal_attribution_established")
        ),
    }


def _refresh_manifest(staging: Path, additions: dict[str, Any]) -> None:
    manifest_path = staging / "run_manifest.json"
    manifest = _json(manifest_path)
    for key in ("cycle_summary_source", "raw_signal_source", "raw_signal_provenance_source"):
        value = manifest.get(key)
        if isinstance(value, dict) and "path" in value:
            value["path"] = {
                "cycle_summary_source": "${IMPORT_OUTPUT}/nasa_pcoe_cycle_summary.csv",
                "raw_signal_source": "${IMPORT_OUTPUT}/nasa_pcoe_raw_signal.csv",
                "raw_signal_provenance_source": "${IMPORT_OUTPUT}/nasa_pcoe_raw_signal_provenance.json",
            }[key]
    manifest["audit_bundle_preparation"] = additions
    manifest["packaging_runtime_environment"] = runtime_environment()
    artifact_paths = sorted(
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file()
        and path.name not in {"run_manifest.json", "_audit_bundle_inventory.csv", "_audit_bundle_readme.txt"}
    )
    manifest["artifact_paths"] = artifact_paths
    manifest["artifact_checksums"] = {
        relative: file_sha256(staging / relative) for relative in artifact_paths
    }
    manifest["artifact_byte_count"] = {
        relative: int((staging / relative).stat().st_size) for relative in artifact_paths
    }
    manifest["artifact_inventory_policy"] = (
        "all staged files except the self-referential run manifest and package inventory/readme"
    )
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    analysis_output = args.analysis_output.resolve()
    staging = args.staging_root.resolve()
    if not analysis_output.is_dir() or not staging.is_dir():
        raise FileNotFoundError("analysis output and staging root must exist")
    manifest = _json(analysis_output / "run_manifest.json")
    import_output = args.import_output.resolve() if args.import_output else _infer_import_output(manifest)
    raw_directory = args.raw_directory.resolve() if args.raw_directory else None
    if raw_directory is None and import_output is not None:
        candidate = import_output.parent.parent / "raw" / "battery" / "nasa_pcoe"
        if candidate.is_dir():
            raw_directory = candidate.resolve()

    import_files = _copy_tree(
        import_output, staging / "import_audit" / "import_output"
    ) if import_output is not None else []
    source_files = _copy_source_evidence(
        raw_directory, staging / "import_audit" / "source"
    ) if raw_directory is not None else []
    disposition = _install_disposition(staging, args.disposition_input)
    diagnostics = augment_audit_diagnostics(staging)
    charge_semantics = diagnostics["charge_feature_semantics"]
    source_cohort = diagnostics["source_cohort_validation"]
    coverage = diagnostics["coverage_diagnostics"]
    target_sensitivity = diagnostics["target_reference_sensitivity"]
    external_gate = {
        "status": "blocked_external_evidence_required",
        "reason": (
            "No independent compatible external cohort was supplied. Source-cohort-disjoint NASA validation cannot be relabeled external validation."
        ),
        "required_compatibility_fields": [
            "cell chemistry",
            "rated/reference capacity definition",
            "cycling protocol",
            "temperature",
            "measurement units",
            "battery identity",
            "raw-signal semantics",
        ],
    }
    (staging / "reports" / "external_validation_gate.json").write_text(
        canonical_json(external_gate), encoding="utf-8"
    )

    additions = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_path_redacted": True,
        "self_contained_import_output": bool(import_files),
        "included_import_file_count": len(import_files),
        "included_source_files": source_files,
        "original_source_archive_included": "5_Battery_Data_Set.zip" in source_files,
        "retrieval_receipt_included": "retrieval_receipt.json" in source_files,
        "completed_disposition": disposition,
        "charge_feature_semantics": charge_semantics,
        "source_cohort_validation": source_cohort,
        "coverage_diagnostics": coverage,
        "target_reference_sensitivity": target_sensitivity,
        "external_validation_gate": external_gate,
        "scientific_boundary": (
            "The audit package verifies reproducibility and internal cohort stress tests. It does not establish external predictive validity, causality, or engineering readiness."
        ),
    }
    roots = _redaction_roots(analysis_output, import_output, raw_directory)
    additions["redacted_file_count"] = len(_redact_staged_text(staging, roots))
    _refresh_manifest(staging, additions)
    _redact_staged_text(staging, roots)
    remaining = _remaining_absolute_paths(staging)
    if remaining:
        preview = "; ".join(
            f"{item['relative_path']}:{item['matched_path']}" for item in remaining[:5]
        )
        raise ValueError(f"absolute paths remain after redaction: {preview}")
    print(canonical_json(additions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
