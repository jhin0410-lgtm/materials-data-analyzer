from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.nist_amb2025_03_fatigue_intake import (
    NistAmb202503FatigueIntakeError,
    audit_amb2025_03_fatigue,
)

FATIGUE_WORKBOOK = "calibration_data/fatigue_testing/fatigue_800hip.xlsx"
FATIGUE_README = "calibration_data/fatigue_testing/readme.txt"


class LiveAmb202503AuditError(ValueError):
    pass


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveAmb202503AuditError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LiveAmb202503AuditError(f"JSON root must be an object: {path}")
    return value


def _exact_artifact(report: dict, artifact_path: str) -> tuple[bytes, dict]:
    acquisition = report.get("acquisition")
    if not isinstance(acquisition, dict):
        raise LiveAmb202503AuditError("frontier report lacks acquisition object")
    receipts = acquisition.get("receipts")
    if not isinstance(receipts, list):
        raise LiveAmb202503AuditError("frontier report receipts must be a list")
    matches = [
        item
        for item in receipts
        if isinstance(item, dict) and item.get("artifact_path") == artifact_path
    ]
    if len(matches) != 1:
        raise LiveAmb202503AuditError(
            f"expected one authenticated receipt for {artifact_path!r}, got {len(matches)}"
        )
    receipt = matches[0]
    if receipt.get("recorded_acquisition_provenance_authenticated") is not True:
        raise LiveAmb202503AuditError(f"receipt is not provenance-authenticated: {artifact_path}")
    if receipt.get("scientific_status_changed") is not False:
        raise LiveAmb202503AuditError(f"acquisition changed scientific status: {artifact_path}")
    package = Path(str(receipt.get("package_directory", "")))
    source = package / artifact_path
    try:
        body = source.read_bytes()
    except OSError as exc:
        raise LiveAmb202503AuditError(f"could not read acquired artifact {source}: {exc}") from exc
    if len(body) != receipt.get("artifact_size_bytes"):
        raise LiveAmb202503AuditError(f"artifact size changed after acquisition: {artifact_path}")
    if hashlib.sha256(body).hexdigest() != receipt.get("artifact_sha256"):
        raise LiveAmb202503AuditError(f"artifact SHA-256 changed after acquisition: {artifact_path}")
    return body, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        frontier = _load_json(args.acquisition_root / "frontier_acquisition_report.json")
        acquisition = frontier.get("acquisition")
        if not isinstance(acquisition, dict):
            raise LiveAmb202503AuditError("frontier report lacks acquisition object")
        if acquisition.get("all_auto_succeeded") is not True:
            raise LiveAmb202503AuditError("scientific intake requires all predeclared source files")
        if frontier.get("scientific_status_changed") is not False:
            raise LiveAmb202503AuditError("frontier acquisition changed scientific status")
        workbook_bytes, workbook_receipt = _exact_artifact(frontier, FATIGUE_WORKBOOK)
        readme_bytes, readme_receipt = _exact_artifact(frontier, FATIGUE_README)
        report = audit_amb2025_03_fatigue(
            workbook_bytes=workbook_bytes,
            readme_bytes=readme_bytes,
        )
        report["acquisition_binding"] = {
            "frontier_candidate_id": frontier.get("frontier_candidate_id"),
            "metadata_sha256": acquisition.get("metadata_sha256"),
            "workbook_receipt_sha256": hashlib.sha256(
                json.dumps(workbook_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "readme_receipt_sha256": hashlib.sha256(
                json.dumps(readme_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "recorded_acquisition_provenance_authenticated": True,
        }
        summary = {
            "dataset": "NIST AMB2025-03 Ti-6Al-4V 800HIP fatigue",
            "doi": report["source"]["doi"],
            "workbook_sha256": report["source"]["workbook_sha256"],
            "test_rows": report["fatigue_inventory"]["test_rows"],
            "valid_failure_or_runout_specimens": report["fatigue_inventory"][
                "valid_failure_or_runout_specimens"
            ],
            "observed_failures": report["fatigue_inventory"]["observed_failures"],
            "runouts": report["fatigue_inventory"]["runouts"],
            "invalid_tests": report["fatigue_inventory"]["invalid_tests"],
            "exact_integer_censor_cycles_from_notes": report["runout_reconciliation"][
                "exact_integer_censor_cycles_from_notes"
            ],
            "million_shorthand_rows_requiring_semantic_review": report[
                "runout_reconciliation"
            ]["million_shorthand_rows_requiring_semantic_review"],
            "cycles_column_vs_exact_note_discrepancy_count": report[
                "runout_reconciliation"
            ]["cycles_column_vs_exact_note_discrepancy_count"],
            "naive_uncensored_cycles_regression_eligible": report[
                "analysis_eligibility"
            ]["naive_uncensored_cycles_regression"]["eligible"],
            "condition_specific_censored_sn_analysis_eligible": report[
                "analysis_eligibility"
            ]["condition_specific_censored_sn_analysis"]["eligible"],
            "scientific_support_established": report["scientific_support_established"],
            "scientific_status_changed": report["scientific_status_changed"],
        }
    except (
        LiveAmb202503AuditError,
        NistAmb202503FatigueIntakeError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
    ) as exc:
        print(f"AMB2025-03 fatigue scientific intake failed closed: {exc}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "fatigue_scientific_intake_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output / "fatigue_scientific_intake_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
