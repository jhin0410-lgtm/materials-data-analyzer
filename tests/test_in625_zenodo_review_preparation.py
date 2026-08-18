from __future__ import annotations

import hashlib

import pytest

from materials_data_analyzer.research_loop.in625_zenodo_review_preparation import (
    In625ZenodoReviewPreparationError,
    prepare_in625_zenodo_review_packet,
)


SHA = "a" * 64
TEXT = "method=ball-on-disc\n"
TEXT_SHA = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
TEXT_SIZE = len(TEXT.encode("utf-8"))
TEXT_LINE_COUNT = len(TEXT.splitlines())


def _inputs():
    candidate = {
        "candidate_id": "federated-evidence:test",
        "artifact_sha256": SHA,
        "provider": "zenodo",
        "source_id": "zenodo:20503603",
        "evidence_class": "E2_publication_supplement",
        "scientific_status_changed": False,
    }
    ceiling = {
        "candidate_id": "federated-evidence:test",
        "blocker_codes": ["sample_identity_not_exact", "calibration_status_unknown"],
        "scientific_status_changed": False,
    }
    summary = {
        "record_id": "20503603",
        "doi": "10.5281/zenodo.20503603",
        "related_article_doi": "10.1016/j.jmrt.2026.05.163",
        "related_article_relation_verified_from_record": True,
        "evidence_candidate_id": "federated-evidence:test",
        "remaining_blocker_codes": [
            "sample_acquisition_lineage_not_yet_bound",
            "measurement_semantics_and_calibration_not_yet_audited",
            "human_scientific_review_not_yet_released",
        ],
        "scientific_status_changed": False,
    }
    inventory = {
        "archive_sha256": SHA,
        "bulk_extraction_performed": False,
        "scientific_status_changed": False,
        "members": [
            {
                "path": "Dataset/Tribological testing/README.txt",
                "is_directory": False,
                "suffix": ".txt",
                "uncompressed_size_bytes": TEXT_SIZE,
                "text_sha256": TEXT_SHA,
            },
            {
                "path": "Dataset/Mechanical testing/Tensile tests/data.xlsx",
                "is_directory": False,
                "suffix": ".xlsx",
                "text_sha256": None,
            },
        ],
    }
    readout = {
        "archive_sha256": SHA,
        "bulk_extraction_performed": False,
        "scientific_status_changed": False,
        "members": [
            {
                "path": "Dataset/Tribological testing/README.txt",
                "sha256": TEXT_SHA,
                "size_bytes": TEXT_SIZE,
                "line_count": TEXT_LINE_COUNT,
                "text": TEXT,
            }
        ],
    }
    return candidate, ceiling, summary, inventory, readout


def test_builds_review_request_but_never_review_decision_or_scientific_support() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    packet = prepare_in625_zenodo_review_packet(
        candidate=candidate,
        use_ceiling=ceiling,
        live_summary=summary,
        archive_inventory=inventory,
        selected_text_readout=readout,
    )
    assert packet["review_request"]["requested_uses"] == ["scientific_intake"]
    assert packet["human_review_decision_created"] is False
    assert packet["human_review_blocker_released"] is False
    assert packet["scientific_support_established"] is False
    assert packet["issue_76_eligible"] is False
    assert packet["semantic_contract"]["proposal_only"] is True
    assert packet["lineage_proposal"]["filename_token_inference_authorized"] is False
    assert packet["intake_artifact"]["descriptive_analysis_authorized"] is False


def test_trailing_newline_is_preserved_while_exact_text_sha_is_reverified() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    packet = prepare_in625_zenodo_review_packet(
        candidate=candidate,
        use_ceiling=ceiling,
        live_summary=summary,
        archive_inventory=inventory,
        selected_text_readout=readout,
    )
    witness = packet["semantic_contract"]["bounded_text_witnesses"][0]
    assert witness["sha256"] == TEXT_SHA
    assert witness["size_bytes"] == TEXT_SIZE
    assert witness["line_count"] == TEXT_LINE_COUNT
    assert witness["text_preview"] == TEXT
    assert witness["text_sha256_reverified"] is True


def test_archive_path_groups_are_navigation_candidates_not_semantics() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    packet = prepare_in625_zenodo_review_packet(
        candidate=candidate,
        use_ceiling=ceiling,
        live_summary=summary,
        archive_inventory=inventory,
        selected_text_readout=readout,
    )
    families = packet["semantic_contract"]["archive_family_candidates"]
    labels = {item["archive_family_candidate"] for item in families}
    assert "Tribological testing" in labels
    assert "Mechanical testing/Tensile tests" in labels
    assert all(item["path_group_is_not_validated_measurement_semantics"] for item in families)


def test_mismatched_archive_sha_fails_closed() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    readout["archive_sha256"] = "c" * 64
    with pytest.raises(In625ZenodoReviewPreparationError, match="archive bytes"):
        prepare_in625_zenodo_review_packet(
            candidate=candidate,
            use_ceiling=ceiling,
            live_summary=summary,
            archive_inventory=inventory,
            selected_text_readout=readout,
        )


def test_mutated_text_with_stale_declared_sha_fails_closed() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    readout["members"][0]["text"] = "method=pin-on-disc\n"
    readout["members"][0]["size_bytes"] = len(readout["members"][0]["text"].encode("utf-8"))
    readout["members"][0]["line_count"] = len(readout["members"][0]["text"].splitlines())
    with pytest.raises(In625ZenodoReviewPreparationError, match="body SHA-256"):
        prepare_in625_zenodo_review_packet(
            candidate=candidate,
            use_ceiling=ceiling,
            live_summary=summary,
            archive_inventory=inventory,
            selected_text_readout=readout,
        )


def test_declared_text_size_mismatch_fails_closed() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    readout["members"][0]["size_bytes"] = TEXT_SIZE + 1
    with pytest.raises(In625ZenodoReviewPreparationError, match="body size"):
        prepare_in625_zenodo_review_packet(
            candidate=candidate,
            use_ceiling=ceiling,
            live_summary=summary,
            archive_inventory=inventory,
            selected_text_readout=readout,
        )


def test_declared_line_count_mismatch_fails_closed() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    readout["members"][0]["line_count"] = TEXT_LINE_COUNT + 1
    with pytest.raises(In625ZenodoReviewPreparationError, match="line count"):
        prepare_in625_zenodo_review_packet(
            candidate=candidate,
            use_ceiling=ceiling,
            live_summary=summary,
            archive_inventory=inventory,
            selected_text_readout=readout,
        )


def test_review_packet_preserves_semantic_and_lineage_unknowns() -> None:
    candidate, ceiling, summary, inventory, readout = _inputs()
    packet = prepare_in625_zenodo_review_packet(
        candidate=candidate,
        use_ceiling=ceiling,
        live_summary=summary,
        archive_inventory=inventory,
        selected_text_readout=readout,
    )
    semantic = packet["semantic_contract"]["unresolved_semantic_fields"]
    lineage = packet["lineage_proposal"]["unresolved_lineage_fields"]
    assert "calibration_and_reference_state" in semantic
    assert "specimen_id" in lineage
    assert packet["lineage_proposal"]["replicate_independence_status"] == "unresolved"
    assert packet["scientific_status_changed"] is False
