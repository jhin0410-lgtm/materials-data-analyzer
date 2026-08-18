from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.live_real_data_mvp import (
    LiveRealDataMvpError,
    build_live_real_data_mvp_suite,
)


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write(path: Path, content: str = "evidence\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _consumer(
    root: Path,
    *,
    case_id: str,
    bundle_path: Path,
    closeout: dict[str, object],
    feature_summary: dict[str, object] | None = None,
    scientific_metrics_recomputed: bool | None = None,
) -> None:
    software: dict[str, object] = {"model_trained": False}
    if scientific_metrics_recomputed is not None:
        software["scientific_metrics_recomputed"] = scientific_metrics_recomputed
    summary: dict[str, object] = {
        "status": "verified",
        "case_id": case_id,
        "scientific_closeout": closeout,
        "software_validation": software,
    }
    if feature_summary is not None:
        summary["feature_summary"] = feature_summary
    _write_json(root / "cross_repository_handoff_summary.json", summary)
    _write_json(
        root / "cross_repository_handoff_manifest.json",
        {"input_bundle": {"sha256": _sha(bundle_path)}},
    )


def _build_fixture(root: Path) -> dict[str, Path]:
    nasa_raw = root / "nasa" / "raw"
    nasa_import = root / "nasa" / "import"
    nasa_analysis = root / "nasa" / "analysis"
    archive = _write(nasa_raw / "5_Battery_Data_Set.zip", "not-a-real-zip-but-byte-bound-test-fixture")
    _write_json(
        nasa_raw / "retrieval_receipt.json",
        {
            "source_url": "https://example.test/NASA/5.Battery.Data.Set.zip",
            "archive_sha256": _sha(archive),
            "size_bytes": archive.stat().st_size,
            "zip_entry_count": 5,
        },
    )
    _write_json(
        nasa_import / "nasa_pcoe_import_manifest.json",
        {"retrieval_receipt_verified": True, "imported_discharge_operation_count": 12},
    )
    _write_json(
        nasa_analysis / "reports" / "target_comparability_audit.json",
        {
            "target_comparability_flag_battery_count": 2,
            "reference_consistency_flag_battery_count": 1,
            "cycle_gap_battery_count": 1,
        },
    )
    _write_json(
        nasa_analysis / "reports" / "battery_influence_triage.json",
        {"disproportionate_error_contributor_battery_count": 1},
    )
    _write_json(nasa_analysis / "reports" / "scientific_closeout.json", {"evidence_level": "Diagnostic"})
    _write_json(nasa_analysis / "reports" / "nasa_protocol_audit.json", {"protocol_audit_status": "bounded_diagnostic"})
    _write(nasa_analysis / "tables" / "battery_diagnostic_priority.csv", "battery_id,priority\nB1,1\n")

    dwcnt_producer = root / "dwcnt" / "producer"
    dwcnt_consumer = root / "dwcnt" / "consumer"
    _write(dwcnt_producer / "case_source_manifest.json", "{}\n")
    _write(dwcnt_producer / "case_analysis_manifest.json", "{}\n")
    _write(dwcnt_producer / "comparability_matrix.csv", "sample_id,status\npublic-dwcnt,review\n")
    _write(dwcnt_producer / "analyses" / "tga" / "tga_case_candidate_review.csv", "candidate,status\n1,retained\n")
    _write_json(
        dwcnt_producer / "case_summary.json",
        {
            "tga_case_candidate_review": {
                "raw_candidate_count": 3,
                "retained_review_required_count": 2,
                "rejected_startup_boundary_artifact_count": 1,
            }
        },
    )
    dwcnt_bundle = _write_json(
        dwcnt_producer / "characterization_handoff_bundle.json",
        {"case_id": "public-carbon-dwcnt-multimodal-v1"},
    )
    _consumer(
        dwcnt_consumer,
        case_id="public-carbon-dwcnt-multimodal-v1",
        bundle_path=dwcnt_bundle,
        closeout={
            "evidence_level": "Diagnostic",
            "primary_limitation": "Identical physical aliquots are not established across techniques.",
        },
    )

    rwgs_producer = root / "rwgs" / "producer"
    rwgs_validation = root / "rwgs" / "validation"
    rwgs_consumer = root / "rwgs" / "consumer"
    _write(rwgs_producer / "selected_source_manifest.json", "{}\n")
    _write(rwgs_producer / "characterization_manifest.json", "{}\n")
    _write(rwgs_producer / "comparability_matrix.csv", "sample_id,status\nrwgs-5wt-cu-al2o3,review\n")
    rwgs_bundle = _write_json(
        rwgs_producer / "handoff_bundle" / "characterization_handoff_bundle.json",
        {"case_id": "public-rwgs-5cu-al2o3-xrd-sem-eds"},
    )
    _write_json(rwgs_validation / "handoff_bundle_validation_summary.json", {"status": "valid"})
    _consumer(
        rwgs_consumer,
        case_id="public-rwgs-5cu-al2o3-xrd-sem-eds",
        bundle_path=rwgs_bundle,
        closeout={
            "evidence_level": "Diagnostic",
            "result": "public_rwgs_xrd_eds_features_exported_sem_block_preserved",
            "primary_limitation": "Common nominal sample label does not establish identical aliquots; SEM is method-blocked and Ni is unresolved.",
            "unsuitable_for": ["process-response modeling", "causal attribution"],
        },
        feature_summary={
            "row_count": 31,
            "sample_count": 1,
            "measurement_count": 2,
            "instruments": ["eds", "xrd"],
        },
        scientific_metrics_recomputed=False,
    )
    return {
        "nasa_raw_directory": nasa_raw,
        "nasa_import_output": nasa_import,
        "nasa_analysis_output": nasa_analysis,
        "dwcnt_producer_result": dwcnt_producer,
        "dwcnt_consumer_output": dwcnt_consumer,
        "rwgs_producer_result": rwgs_producer,
        "rwgs_producer_validation": rwgs_validation,
        "rwgs_consumer_output": rwgs_consumer,
    }


def test_three_materially_different_real_data_workflows_pass_mvp_contract(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    result = build_live_real_data_mvp_suite(**paths)
    acceptance = result["suite_acceptance"]
    assert acceptance["mvp_acceptance_passed"] is True
    assert acceptance["full_cycle_count"] == 3
    assert acceptance["full_cycle_family_count"] == 3
    assert acceptance["full_cycle_modality_count"] == 3
    assert acceptance["full_cycle_evidence_class_count"] == 2
    assert result["scientific_status_changed"] is False
    assert result["execution_authorized_here"] is False
    assert result["human_review_synthesized_here"] is False
    assert result["issue_76_status_changed_here"] is False
    assert all(report["iteration_count"] == 2 for report in result["episode_reports"])
    assert all(report["scientific_status_changed"] is False for report in result["episode_reports"])


def test_nasa_archive_mutation_after_receipt_fails_closed(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    archive = paths["nasa_raw_directory"] / "5_Battery_Data_Set.zip"
    archive.write_bytes(archive.read_bytes() + b"mutation")
    with pytest.raises(LiveRealDataMvpError, match="archive SHA-256"):
        build_live_real_data_mvp_suite(**paths)


def test_dwcnt_consumer_must_bind_exact_producer_bundle_bytes(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    bundle = paths["dwcnt_producer_result"] / "characterization_handoff_bundle.json"
    bundle.write_text('{"case_id":"public-carbon-dwcnt-multimodal-v1","mutated":true}\n', encoding="utf-8")
    with pytest.raises(LiveRealDataMvpError, match="input bundle SHA"):
        build_live_real_data_mvp_suite(**paths)


def test_dwcnt_second_pass_review_must_reconcile(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    summary = paths["dwcnt_producer_result"] / "case_summary.json"
    _write_json(
        summary,
        {
            "tga_case_candidate_review": {
                "raw_candidate_count": 3,
                "retained_review_required_count": 3,
                "rejected_startup_boundary_artifact_count": 1,
            }
        },
    )
    with pytest.raises(LiveRealDataMvpError, match="do not reconcile"):
        build_live_real_data_mvp_suite(**paths)


def test_rwgs_sem_method_boundary_cannot_be_silently_removed(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    summary_path = paths["rwgs_consumer_output"] / "cross_repository_handoff_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["scientific_closeout"]["result"] = "sem_quantitative_result_exported"
    _write_json(summary_path, summary)
    with pytest.raises(LiveRealDataMvpError, match="method-mismatch boundary"):
        build_live_real_data_mvp_suite(**paths)


def test_rwgs_model_training_or_metric_recomputation_is_not_accepted(tmp_path: Path) -> None:
    paths = _build_fixture(tmp_path)
    summary_path = paths["rwgs_consumer_output"] / "cross_repository_handoff_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["software_validation"]["model_trained"] = True
    _write_json(summary_path, summary)
    with pytest.raises(LiveRealDataMvpError, match="model_trained"):
        build_live_real_data_mvp_suite(**paths)
