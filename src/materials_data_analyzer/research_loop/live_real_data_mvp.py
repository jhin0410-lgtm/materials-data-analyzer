"""Compile fail-closed MVP episode reports from three live public-data workflows.

This module does not acquire evidence or perform scientific promotion. It consumes artifacts
created by the existing NASA battery and cross-repository characterization workflows, verifies
critical byte/provenance bindings again, and translates only observed diagnostic work into the
real-data episode acceptance contract.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .real_data_episode_acceptance import evaluate_real_data_episode_suite

LIVE_REAL_DATA_MVP_SCHEMA_VERSION = "1.0"
LIVE_REAL_DATA_MVP_POLICY_VERSION = "1.0"


class LiveRealDataMvpError(ResearchLoopError):
    """Raised when live workflow evidence is missing, malformed, or no longer byte-bound."""


def _canonical_sha256(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LiveRealDataMvpError("MVP evidence must be canonical-JSON serializable") from exc
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise LiveRealDataMvpError(f"{label} must not be a symbolic link: {path}")
    if not path.is_file():
        raise LiveRealDataMvpError(f"{label} not found: {path}")
    return path


def _json(path: Path, label: str) -> dict[str, Any]:
    source = _file(path, label)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LiveRealDataMvpError(f"could not read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise LiveRealDataMvpError(f"{label} must contain a JSON object")
    return value


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveRealDataMvpError(f"{label} must be an object")
    return dict(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveRealDataMvpError(f"{label} must be non-empty text")
    return value.strip()


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LiveRealDataMvpError(f"{label} must be a positive integer")
    return value


def _require_false(value: object, label: str) -> None:
    if value is not False:
        raise LiveRealDataMvpError(f"{label} must remain false")


def _require_true(value: object, label: str) -> None:
    if value is not True:
        raise LiveRealDataMvpError(f"{label} must be true")


def _next_action(action_type: str, rationale: str, evidence_sha256: list[str]) -> tuple[dict[str, Any], str]:
    record = {
        "action_type": action_type,
        "rationale": rationale,
        "evidence_sha256": sorted(evidence_sha256),
        "execution_authorized_here": False,
        "physical_experiment_executed_here": False,
        "scientific_status_changed": False,
    }
    return record, _canonical_sha256(record)


def _base_report(
    *,
    episode_id: str,
    family: str,
    modality: str,
    evidence_class: str,
    source_kind: str,
    source_locator: str,
    artifact_sha256: str,
    acquisition_receipt_sha256: str | None,
    research_question: str,
    intake_reason: str,
    weaknesses: list[str],
    next_action_record: dict[str, Any],
    next_action_sha256: str,
    terminal_reason: str,
    observed_artifacts: dict[str, str],
) -> dict[str, Any]:
    return {
        "episode_id": episode_id,
        "episode_family_id": family,
        "modality": modality,
        "evidence_class": evidence_class,
        "real_source_binding": {
            "source_kind": source_kind,
            "source_locator": source_locator,
            "artifact_sha256": artifact_sha256,
            "acquisition_receipt_sha256": acquisition_receipt_sha256,
            "synthetic": False,
        },
        "research_question": research_question,
        "scientific_intake": {
            "status": "accepted",
            "reason": intake_reason,
        },
        "analysis": {
            "performed": True,
            "scope": "diagnostic_only",
            "scientific_promotion_performed": False,
        },
        "weaknesses_or_contradictions": weaknesses,
        "next_action_decision": {
            "decision_report_sha256": next_action_sha256,
            "action_recorded": True,
        },
        "next_action_record": next_action_record,
        "iteration_count": 2,
        "terminal_state": "stopped",
        "terminal_reason": terminal_reason,
        "scientific_status_changed": False,
        "scientific_promotion_authorized": False,
        "observed_artifacts": observed_artifacts,
    }


def build_nasa_battery_episode(
    *,
    raw_directory: str | Path,
    import_output: str | Path,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Bind the official NASA archive, importer, first analysis, and protocol re-audit."""
    raw = Path(raw_directory)
    imported = Path(import_output)
    analysis = Path(analysis_output)
    archive = _file(raw / "5_Battery_Data_Set.zip", "NASA archive")
    receipt_path = _file(raw / "retrieval_receipt.json", "NASA retrieval receipt")
    receipt = _json(receipt_path, "NASA retrieval receipt")

    observed_archive_sha = _sha256_file(archive)
    if receipt.get("archive_sha256") != observed_archive_sha:
        raise LiveRealDataMvpError("NASA retrieval receipt archive SHA-256 does not match live bytes")
    if receipt.get("size_bytes") != archive.stat().st_size:
        raise LiveRealDataMvpError("NASA retrieval receipt size does not match live archive bytes")
    _positive_int(receipt.get("zip_entry_count"), "NASA retrieval receipt zip_entry_count")

    import_manifest_path = imported / "nasa_pcoe_import_manifest.json"
    target_audit_path = analysis / "reports" / "target_comparability_audit.json"
    triage_path = analysis / "reports" / "battery_influence_triage.json"
    closeout_path = analysis / "reports" / "scientific_closeout.json"
    protocol_path = analysis / "reports" / "nasa_protocol_audit.json"
    priority_path = _file(
        analysis / "tables" / "battery_diagnostic_priority.csv",
        "NASA diagnostic-priority table",
    )
    import_manifest = _json(import_manifest_path, "NASA import manifest")
    target_audit = _json(target_audit_path, "NASA target comparability audit")
    triage = _json(triage_path, "NASA influence triage")
    closeout = _json(closeout_path, "NASA scientific closeout")
    protocol = _json(protocol_path, "NASA protocol audit")

    _require_true(import_manifest.get("retrieval_receipt_verified"), "NASA retrieval_receipt_verified")
    _positive_int(
        import_manifest.get("imported_discharge_operation_count"),
        "NASA imported_discharge_operation_count",
    )
    _text(closeout.get("evidence_level"), "NASA closeout evidence_level")
    _text(protocol.get("protocol_audit_status"), "NASA protocol_audit_status")

    observed = {
        "archive_sha256": observed_archive_sha,
        "retrieval_receipt_sha256": _sha256_file(receipt_path),
        "import_manifest_sha256": _sha256_file(_file(import_manifest_path, "NASA import manifest")),
        "target_comparability_audit_sha256": _sha256_file(_file(target_audit_path, "NASA target audit")),
        "battery_influence_triage_sha256": _sha256_file(_file(triage_path, "NASA triage")),
        "scientific_closeout_sha256": _sha256_file(_file(closeout_path, "NASA closeout")),
        "protocol_audit_sha256": _sha256_file(_file(protocol_path, "NASA protocol audit")),
        "diagnostic_priority_sha256": _sha256_file(priority_path),
    }
    weaknesses = [
        "protocol_aware_audit_required_before_predictive_claims",
        "target_comparability_and_battery_influence_are_explicit_diagnostic_limits",
    ]
    for field in (
        "target_comparability_flag_battery_count",
        "reference_consistency_flag_battery_count",
        "cycle_gap_battery_count",
    ):
        value = target_audit.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            weaknesses.append(f"{field}:{value}")
    influence = triage.get("disproportionate_error_contributor_battery_count")
    if isinstance(influence, int) and not isinstance(influence, bool) and influence > 0:
        weaknesses.append(f"disproportionate_error_contributor_battery_count:{influence}")

    action, action_sha = _next_action(
        "retain_diagnostic_scope_and_prioritize_protocol_or_source_quality_followup",
        "The first battery analysis was re-audited against protocol, target-comparability, and battery-level influence evidence before bounded stop.",
        [observed["target_comparability_audit_sha256"], observed["protocol_audit_sha256"], observed["diagnostic_priority_sha256"]],
    )
    return _base_report(
        episode_id="live-nasa-pcoe-battery-v1",
        family="nasa-pcoe-battery",
        modality="battery_degradation_and_protocol_audit",
        evidence_class="E0_raw_experiment",
        source_kind="official_public_raw_experiment_archive",
        source_locator=_text(receipt.get("source_url"), "NASA source_url"),
        artifact_sha256=observed_archive_sha,
        acquisition_receipt_sha256=observed["retrieval_receipt_sha256"],
        research_question="What battery-degradation signal is supported by the checksum-bound NASA PCoE archive, and what protocol or comparability limits survive re-audit?",
        intake_reason="Official public archive bytes matched their retrieval receipt and the NASA importer explicitly verified the receipt before diagnostic analysis.",
        weaknesses=weaknesses,
        next_action_record=action,
        next_action_sha256=action_sha,
        terminal_reason="battery_analysis_and_protocol_reaudit_completed_with_predictive_claims_kept_bounded",
        observed_artifacts=observed,
    )


def _verified_consumer_bundle(
    *,
    producer_bundle_manifest: Path,
    consumer_output: Path,
    expected_case_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    bundle = _json(producer_bundle_manifest, "producer handoff bundle manifest")
    summary_path = consumer_output / "cross_repository_handoff_summary.json"
    manifest_path = consumer_output / "cross_repository_handoff_manifest.json"
    summary = _json(summary_path, "consumer handoff summary")
    manifest = _json(manifest_path, "consumer handoff manifest")
    if bundle.get("case_id") != expected_case_id or summary.get("case_id") != expected_case_id:
        raise LiveRealDataMvpError(f"unexpected characterization case identity for {expected_case_id}")
    if summary.get("status") != "verified":
        raise LiveRealDataMvpError(f"consumer handoff is not verified for {expected_case_id}")
    input_bundle = _mapping(manifest.get("input_bundle"), "consumer input_bundle")
    bundle_sha = _sha256_file(producer_bundle_manifest)
    if input_bundle.get("sha256") != bundle_sha:
        raise LiveRealDataMvpError(f"consumer input bundle SHA does not match producer bytes for {expected_case_id}")
    closeout = _mapping(summary.get("scientific_closeout"), "consumer scientific_closeout")
    if closeout.get("evidence_level") != "Diagnostic":
        raise LiveRealDataMvpError(f"{expected_case_id} must remain Diagnostic evidence")
    observed = {
        "producer_bundle_manifest_sha256": bundle_sha,
        "consumer_summary_sha256": _sha256_file(_file(summary_path, "consumer summary")),
        "consumer_manifest_sha256": _sha256_file(_file(manifest_path, "consumer manifest")),
    }
    return bundle, summary, manifest, observed


def build_dwcnt_episode(
    *,
    producer_result: str | Path,
    consumer_output: str | Path,
) -> dict[str, Any]:
    """Bind public DWCNT multimodal analysis plus explicit second-pass TGA review."""
    producer = Path(producer_result)
    consumer = Path(consumer_output)
    source_manifest_path = _file(producer / "case_source_manifest.json", "DWCNT source manifest")
    analysis_manifest_path = _file(producer / "case_analysis_manifest.json", "DWCNT analysis manifest")
    comparability_path = _file(producer / "comparability_matrix.csv", "DWCNT comparability matrix")
    case_summary_path = producer / "case_summary.json"
    case_summary = _json(case_summary_path, "DWCNT case summary")
    tga_review_path = _file(
        producer / "analyses" / "tga" / "tga_case_candidate_review.csv",
        "DWCNT TGA case-level review",
    )
    review = _mapping(case_summary.get("tga_case_candidate_review"), "DWCNT TGA candidate review")
    raw_count = _positive_int(review.get("raw_candidate_count"), "DWCNT raw TGA candidate count")
    retained = review.get("retained_review_required_count")
    rejected = review.get("rejected_startup_boundary_artifact_count")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (retained, rejected)):
        raise LiveRealDataMvpError("DWCNT TGA review counts must be non-negative integers")
    if int(retained) + int(rejected) != raw_count:
        raise LiveRealDataMvpError("DWCNT TGA review counts do not reconcile to raw candidates")

    bundle_path = producer / "characterization_handoff_bundle.json"
    bundle, summary, _manifest, observed = _verified_consumer_bundle(
        producer_bundle_manifest=bundle_path,
        consumer_output=consumer,
        expected_case_id="public-carbon-dwcnt-multimodal-v1",
    )
    software = _mapping(summary.get("software_validation"), "DWCNT software_validation")
    _require_false(software.get("model_trained"), "DWCNT model_trained")
    closeout = _mapping(summary.get("scientific_closeout"), "DWCNT scientific_closeout")
    limitation = _text(closeout.get("primary_limitation"), "DWCNT primary_limitation")

    observed.update(
        {
            "source_manifest_sha256": _sha256_file(source_manifest_path),
            "analysis_manifest_sha256": _sha256_file(analysis_manifest_path),
            "comparability_matrix_sha256": _sha256_file(comparability_path),
            "case_summary_sha256": _sha256_file(_file(case_summary_path, "DWCNT case summary")),
            "tga_case_review_sha256": _sha256_file(tga_review_path),
        }
    )
    action, action_sha = _next_action(
        "resolve_cross_technique_aliquot_lineage_and_review_retained_tga_candidates",
        limitation,
        [observed["source_manifest_sha256"], observed["comparability_matrix_sha256"], observed["tga_case_review_sha256"]],
    )
    return _base_report(
        episode_id="live-public-dwcnt-multimodal-v1",
        family="public-dwcnt-characterization",
        modality="multimodal_spectroscopy_thermal_surface_characterization",
        evidence_class="E1_processed_experiment",
        source_kind="checksum_bound_processed_characterization_with_public_raw_source_manifest",
        source_locator="doi:10.57745/7KA2UG",
        artifact_sha256=observed["producer_bundle_manifest_sha256"],
        acquisition_receipt_sha256=None,
        research_question="Which diagnostic multimodal features are reproducibly supported for the public DWCNT sample, and which candidate interpretations fail a second-pass quality review?",
        intake_reason="The public-source feature bundle retained file-level checksums and preprocessing identifiers, passed the independent consumer contract, and was admitted only for Diagnostic use.",
        weaknesses=[
            limitation,
            "cross_technique_identical_physical_aliquot_not_established",
            "tem_quantitative_segmentation_blocked_for_intertwined_cnts_on_holey_support",
            f"tga_second_pass_retained_review_required:{int(retained)}",
            f"tga_second_pass_rejected_startup_artifacts:{int(rejected)}",
        ],
        next_action_record=action,
        next_action_sha256=action_sha,
        terminal_reason="multimodal_analysis_and_explicit_tga_candidate_reanalysis_completed_at_diagnostic_scope",
        observed_artifacts=observed,
    )


def build_rwgs_episode(
    *,
    producer_result: str | Path,
    producer_validation: str | Path,
    consumer_output: str | Path,
) -> dict[str, Any]:
    """Bind public RWGS characterization plus independent bundle/comparability re-review."""
    producer = Path(producer_result)
    validation = Path(producer_validation)
    consumer = Path(consumer_output)
    source_manifest_path = _file(producer / "selected_source_manifest.json", "RWGS source manifest")
    analysis_manifest_path = _file(producer / "characterization_manifest.json", "RWGS analysis manifest")
    comparability_path = _file(producer / "comparability_matrix.csv", "RWGS comparability matrix")
    validation_summary_path = _file(
        validation / "handoff_bundle_validation_summary.json",
        "RWGS independent handoff validation summary",
    )
    bundle_path = producer / "handoff_bundle" / "characterization_handoff_bundle.json"
    _bundle, summary, _manifest, observed = _verified_consumer_bundle(
        producer_bundle_manifest=bundle_path,
        consumer_output=consumer,
        expected_case_id="public-rwgs-5cu-al2o3-xrd-sem-eds",
    )
    feature = _mapping(summary.get("feature_summary"), "RWGS feature_summary")
    if feature.get("row_count") != 31 or feature.get("sample_count") != 1 or feature.get("measurement_count") != 2:
        raise LiveRealDataMvpError("RWGS feature identity/count contract changed")
    if feature.get("instruments") != ["eds", "xrd"]:
        raise LiveRealDataMvpError("RWGS exported instrument contract changed")
    software = _mapping(summary.get("software_validation"), "RWGS software_validation")
    _require_false(software.get("model_trained"), "RWGS model_trained")
    _require_false(software.get("scientific_metrics_recomputed"), "RWGS scientific_metrics_recomputed")
    closeout = _mapping(summary.get("scientific_closeout"), "RWGS scientific_closeout")
    if closeout.get("result") != "public_rwgs_xrd_eds_features_exported_sem_block_preserved":
        raise LiveRealDataMvpError("RWGS SEM method-mismatch boundary is no longer preserved")
    unsuitable = closeout.get("unsuitable_for")
    if not isinstance(unsuitable, list) or "process-response modeling" not in unsuitable:
        raise LiveRealDataMvpError("RWGS must remain unsuitable for process-response modeling")
    limitation = _text(closeout.get("primary_limitation"), "RWGS primary_limitation")

    observed.update(
        {
            "source_manifest_sha256": _sha256_file(source_manifest_path),
            "analysis_manifest_sha256": _sha256_file(analysis_manifest_path),
            "comparability_matrix_sha256": _sha256_file(comparability_path),
            "independent_validation_summary_sha256": _sha256_file(validation_summary_path),
        }
    )
    action, action_sha = _next_action(
        "resolve_physical_aliquot_lineage_eds_ni_and_acquisition_metadata_before_modeling",
        limitation,
        [observed["source_manifest_sha256"], observed["comparability_matrix_sha256"], observed["independent_validation_summary_sha256"]],
    )
    return _base_report(
        episode_id="live-public-rwgs-xrd-eds-v1",
        family="public-rwgs-catalyst-characterization",
        modality="xrd_eds_sem_quality_and_comparability_diagnostics",
        evidence_class="E1_processed_experiment",
        source_kind="checksum_bound_processed_characterization_with_public_raw_source_manifest",
        source_locator="doi:10.5281/zenodo.13474908",
        artifact_sha256=observed["producer_bundle_manifest_sha256"],
        acquisition_receipt_sha256=None,
        research_question="Which XRD/EDS/SEM diagnostic statements survive provenance, method-suitability, and cross-technique comparability review for public 5 wt% Cu/Al2O3 RWGS data?",
        intake_reason="The public Zenodo-derived bundle passed producer and independent consumer validation and was admitted only for Diagnostic XRD/EDS and data-quality use while SEM quantitative segmentation remained blocked.",
        weaknesses=[
            limitation,
            "same_nominal_sample_label_does_not_confirm_identical_physical_aliquot",
            "sem_quantitative_segmentation_blocked_method_mismatch",
            "eds_unresolved_unexpected_ni_requires_review",
            "key_xrd_and_eds_acquisition_metadata_remain_absent",
        ],
        next_action_record=action,
        next_action_sha256=action_sha,
        terminal_reason="characterization_analysis_and_independent_quality_comparability_reanalysis_completed_at_diagnostic_scope",
        observed_artifacts=observed,
    )


def build_live_real_data_mvp_suite(
    *,
    nasa_raw_directory: str | Path,
    nasa_import_output: str | Path,
    nasa_analysis_output: str | Path,
    dwcnt_producer_result: str | Path,
    dwcnt_consumer_output: str | Path,
    rwgs_producer_result: str | Path,
    rwgs_producer_validation: str | Path,
    rwgs_consumer_output: str | Path,
) -> dict[str, Any]:
    """Compile and evaluate the three live, materially different research episodes."""
    reports = [
        build_nasa_battery_episode(
            raw_directory=nasa_raw_directory,
            import_output=nasa_import_output,
            analysis_output=nasa_analysis_output,
        ),
        build_dwcnt_episode(
            producer_result=dwcnt_producer_result,
            consumer_output=dwcnt_consumer_output,
        ),
        build_rwgs_episode(
            producer_result=rwgs_producer_result,
            producer_validation=rwgs_producer_validation,
            consumer_output=rwgs_consumer_output,
        ),
    ]
    acceptance = evaluate_real_data_episode_suite(reports, required_full_cycles=3)
    result: dict[str, Any] = {
        "schema_version": LIVE_REAL_DATA_MVP_SCHEMA_VERSION,
        "policy_version": LIVE_REAL_DATA_MVP_POLICY_VERSION,
        "episode_reports": reports,
        "suite_acceptance": acceptance,
        "scientific_status_changed": False,
        "execution_authorized_here": False,
        "human_review_synthesized_here": False,
        "issue_76_status_changed_here": False,
    }
    result["result_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "LIVE_REAL_DATA_MVP_POLICY_VERSION",
    "LIVE_REAL_DATA_MVP_SCHEMA_VERSION",
    "LiveRealDataMvpError",
    "build_dwcnt_episode",
    "build_live_real_data_mvp_suite",
    "build_nasa_battery_episode",
    "build_rwgs_episode",
]
