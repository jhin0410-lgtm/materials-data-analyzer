from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from materials_data_analyzer.research_loop.nist_amb2025_03_answer_audit import (
    NistAmb202503AnswerAuditError,
    audit_amb2025_03_answer_metadata,
)
from materials_data_analyzer.research_loop.nist_amb2025_03_fatigue_intake import (
    NistAmb202503FatigueIntakeError,
    audit_amb2025_03_fatigue,
)
from materials_data_analyzer.research_loop.nist_amb2025_03_metadata_contract import (
    NistAmb202503MetadataContractError,
    validate_amb2025_03_metadata,
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


def _canonical_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: dict) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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
        raise LiveAmb202503AuditError(
            f"receipt is not provenance-authenticated: {artifact_path}"
        )
    if receipt.get("scientific_status_changed") is not False:
        raise LiveAmb202503AuditError(
            f"acquisition changed scientific status: {artifact_path}"
        )
    package = Path(str(receipt.get("package_directory", "")))
    source = package / artifact_path
    try:
        body = source.read_bytes()
    except OSError as exc:
        raise LiveAmb202503AuditError(
            f"could not read acquired artifact {source}: {exc}"
        ) from exc
    if len(body) != receipt.get("artifact_size_bytes"):
        raise LiveAmb202503AuditError(
            f"artifact size changed after acquisition: {artifact_path}"
        )
    if hashlib.sha256(body).hexdigest() != receipt.get("artifact_sha256"):
        raise LiveAmb202503AuditError(
            f"artifact SHA-256 changed after acquisition: {artifact_path}"
        )
    return body, receipt


def _exact_source_metadata(receipt: dict, acquisition: dict) -> bytes:
    package = Path(str(receipt.get("package_directory", "")))
    source = package / "source_metadata.json"
    try:
        body = source.read_bytes()
    except OSError as exc:
        raise LiveAmb202503AuditError(
            f"could not read exact NERDm metadata from {source}: {exc}"
        ) from exc
    observed = hashlib.sha256(body).hexdigest()
    expected_receipt = receipt.get("metadata_sha256")
    expected_acquisition = acquisition.get("metadata_sha256")
    if observed != expected_receipt or observed != expected_acquisition:
        raise LiveAmb202503AuditError(
            "exact source_metadata.json does not match acquisition/receipt metadata SHA-256"
        )
    return body


def _second_pass_reanalysis(
    *,
    initial_report: dict,
    readme_bytes: bytes,
    metadata_bytes: bytes,
) -> dict:
    action = initial_report.get("bounded_next_action")
    if not isinstance(action, dict) or action.get("action_type") != "runout_censor_semantics_audit":
        raise LiveAmb202503AuditError(
            "initial intake no longer selects the predeclared runout-censor audit"
        )
    unresolved = [
        item
        for item in initial_report.get("records", [])
        if isinstance(item, dict)
        and item.get("outcome") == "runout"
        and item.get("censor_parse_status")
        == "million_shorthand_requires_semantic_review"
    ]
    if len(unresolved) != 1:
        raise LiveAmb202503AuditError(
            f"expected one unresolved shorthand runout, got {len(unresolved)}"
        )
    try:
        readme = readme_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LiveAmb202503AuditError("fatigue README must remain UTF-8") from exc

    runout = unresolved[0]
    source_note = runout.get("source_note")
    if source_note != "10M runout":
        raise LiveAmb202503AuditError(
            f"unexpected unresolved runout source note: {source_note!r}"
        )
    explicit_definition_found = (
        "10M runout" in readme and "10,000,000" in readme
    )
    answer_audit = audit_amb2025_03_answer_metadata(metadata_bytes)
    if answer_audit["scientific_status_changed"] is not False:
        raise LiveAmb202503AuditError("answer audit changed scientific status")

    reanalysis = {
        "schema_version": "1.0",
        "initial_report_sha256": initial_report["report_sha256"],
        "selected_next_action": dict(action),
        "runout_censor_reanalysis": {
            "specimen_id_source": runout["specimen_id_source"],
            "test_number": runout["test_number"],
            "source_note": source_note,
            "censor_cycles_exact_before": runout["censor_cycles_exact"],
            "censor_cycles_lower_bound_before": runout["censor_cycles_lower_bound"],
            "exact_10m_definition_found_in_acquired_fatigue_readme": explicit_definition_found,
            "censor_cycles_exact_after": None,
            "resolution_status": (
                "resolved_from_exact_source_text"
                if explicit_definition_found
                else "unresolved_without_inference"
            ),
        },
        "adjacent_answer_data_provenance_audit": answer_audit,
        "weakness_update": {
            "calibration_only_vac_absence_reclassified": (
                "post_challenge_answer_artifact_discovered_but_not_source_checksum_bound"
            ),
            "runout_exact_censor_semantics_resolved": explicit_definition_found,
            "new_provenance_blocker": answer_audit["new_blocker"],
        },
        "bounded_stop": True,
        "bounded_stop_reasons": [
            "one 800HIP runout still lacks exact integer censor semantics in the authenticated acquired source text",
            "the public both-condition answer workbook lacks a source-published SHA-256 in exact NERDm metadata and is therefore not auto-acquired",
            "one PBF-L build does not establish independent build replication",
        ],
        "future_followups": [
            {
                "action": "obtain_exact_runout_censor_semantics",
                "executed_in_this_episode": False,
            },
            {
                "action": "obtain_source_checksum_or_reviewed_integrity_release_for_both_condition_answer_workbook",
                "executed_in_this_episode": False,
            },
            {
                "action": "acquire_independent_build_replication_before_build_generalized_treatment_effect_claim",
                "executed_in_this_episode": False,
            },
        ],
        "model_training_authorized": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    reanalysis["reanalysis_sha256"] = _canonical_sha256(reanalysis)
    return reanalysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        frontier = _load_json(
            args.acquisition_root / "frontier_acquisition_report.json"
        )
        acquisition = frontier.get("acquisition")
        if not isinstance(acquisition, dict):
            raise LiveAmb202503AuditError("frontier report lacks acquisition object")
        if acquisition.get("all_auto_succeeded") is not True:
            raise LiveAmb202503AuditError(
                "scientific intake requires all predeclared source files"
            )
        if frontier.get("scientific_status_changed") is not False:
            raise LiveAmb202503AuditError(
                "frontier acquisition changed scientific status"
            )
        workbook_bytes, workbook_receipt = _exact_artifact(
            frontier, FATIGUE_WORKBOOK
        )
        readme_bytes, readme_receipt = _exact_artifact(frontier, FATIGUE_README)
        metadata_bytes = _exact_source_metadata(workbook_receipt, acquisition)
        source_scope = validate_amb2025_03_metadata(metadata_bytes)
        report = audit_amb2025_03_fatigue(
            workbook_bytes=workbook_bytes,
            readme_bytes=readme_bytes,
        )
        report.pop("report_sha256", None)
        report["source_scope_contract"] = source_scope
        report["acquisition_binding"] = {
            "frontier_candidate_id": frontier.get("frontier_candidate_id"),
            "metadata_sha256": acquisition.get("metadata_sha256"),
            "workbook_receipt_sha256": hashlib.sha256(
                json.dumps(
                    workbook_receipt, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            "readme_receipt_sha256": hashlib.sha256(
                json.dumps(
                    readme_receipt, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            "recorded_acquisition_provenance_authenticated": True,
        }
        report["report_sha256"] = _canonical_sha256(report)
        reanalysis = _second_pass_reanalysis(
            initial_report=report,
            readme_bytes=readme_bytes,
            metadata_bytes=metadata_bytes,
        )
        episode_sequence = {
            "schema_version": "1.0",
            "episode_id": "nist-amb2025-03-ti64-fatigue-generalization",
            "research_question": (
                "What scientifically valid fatigue conclusions can be extracted from the public AMB2025-03 Ti-6Al-4V evidence without misclassifying censoring or manufacturing replication?"
            ),
            "initial_intake_report_sha256": report["report_sha256"],
            "detected_weakness_codes": [
                item["code"] for item in report["detected_weaknesses"]
            ],
            "next_action_type": report["bounded_next_action"]["action_type"],
            "persisted_reanalysis_sha256": reanalysis["reanalysis_sha256"],
            "bounded_stop": reanalysis["bounded_stop"],
            "future_followups_kept_unexecuted": all(
                item["executed_in_this_episode"] is False
                for item in reanalysis["future_followups"]
            ),
            "full_bounded_research_cycle_completed": True,
            "scientific_support_established": False,
            "scientific_status_changed": False,
        }
        episode_sequence["sequence_sha256"] = _canonical_sha256(episode_sequence)
        summary = {
            "dataset": "NIST AMB2025-03 Ti-6Al-4V 800HIP fatigue",
            "doi": report["source"]["doi"],
            "source_version": source_scope["source_version"],
            "metadata_sha256": source_scope["metadata_sha256"],
            "workbook_sha256": report["source"]["workbook_sha256"],
            "one_build_declared": source_scope["one_build_declared"],
            "post_build_conditions": source_scope["post_build_conditions"],
            "test_rows": report["fatigue_inventory"]["test_rows"],
            "valid_failure_or_runout_specimens": report["fatigue_inventory"][
                "valid_failure_or_runout_specimens"
            ],
            "observed_failures": report["fatigue_inventory"][
                "observed_failures"
            ],
            "runouts": report["fatigue_inventory"]["runouts"],
            "invalid_tests": report["fatigue_inventory"]["invalid_tests"],
            "exact_integer_censor_cycles_from_notes": report[
                "runout_reconciliation"
            ]["exact_integer_censor_cycles_from_notes"],
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
            "both_condition_answer_datafile_discovered": reanalysis[
                "adjacent_answer_data_provenance_audit"
            ]["answer_artifact"]["public_datafile_discovered"],
            "both_condition_answer_source_sha256_bound": reanalysis[
                "adjacent_answer_data_provenance_audit"
            ]["answer_artifact"]["source_sha256_bound"],
            "full_bounded_research_cycle_completed": episode_sequence[
                "full_bounded_research_cycle_completed"
            ],
            "scientific_support_established": report[
                "scientific_support_established"
            ],
            "scientific_status_changed": report["scientific_status_changed"],
            "report_sha256": report["report_sha256"],
            "reanalysis_sha256": reanalysis["reanalysis_sha256"],
            "sequence_sha256": episode_sequence["sequence_sha256"],
        }
    except (
        LiveAmb202503AuditError,
        NistAmb202503AnswerAuditError,
        NistAmb202503FatigueIntakeError,
        NistAmb202503MetadataContractError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
    ) as exc:
        print(
            f"AMB2025-03 fatigue scientific intake failed closed: {exc}",
            file=sys.stderr,
        )
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "fatigue_scientific_intake_report.json").write_bytes(
        _canonical_bytes(report)
    )
    (args.output / "fatigue_second_pass_reanalysis.json").write_bytes(
        _canonical_bytes(reanalysis)
    )
    (args.output / "fatigue_episode_sequence.json").write_bytes(
        _canonical_bytes(episode_sequence)
    )
    (args.output / "fatigue_scientific_intake_summary.json").write_bytes(
        _canonical_bytes(summary)
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
