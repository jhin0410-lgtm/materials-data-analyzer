from __future__ import annotations

import zipfile

import pytest

from materials_data_analyzer.research_loop.archive_tabular_triage import (
    ArchiveTabularTriageError,
    triage_verified_archive_tables,
)
from materials_data_analyzer.research_loop.safe_archive_inventory import inspect_zip_archive


def _archive(tmp_path, *, include_large: bool = False):
    path = tmp_path / "dataset.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", "This archive contains measurements.\nNo table here.\n")
        archive.writestr("data.csv", "sample_id,value\ns1,1.0\ns2,2.0\n")
        archive.writestr("nested/trace.tsv", "time_s\tvoltage_v\n0.0\t1.01\n0.2\t1.00\n")
        archive.writestr("notes.dat", "instrument notes only\nsecond prose line\n")
        if include_large:
            archive.writestr("large.csv", "x,y\n" + "1,2\n" * 100)
    return path


def test_archive_triage_discovers_tables_without_source_specific_member_names(tmp_path):
    archive_path = _archive(tmp_path)
    prior = inspect_zip_archive(archive_path)

    report = triage_verified_archive_tables(archive_path, prior)

    assert report["fresh_inventory_revalidated"] is True
    assert report["archive_sha256"] == prior["archive_sha256"]
    assert report["eligible_text_candidate_count"] == 4
    assert report["verified_member_read_count"] == 4
    assert report["tabular_candidate_count"] == 2
    assert report["not_safely_tabular_count"] == 2
    assert [item["path"] for item in report["proposal_only_ranking"]] == [
        "nested/trace.tsv",
        "data.csv",
    ]
    assert report["bulk_extraction_performed"] is False
    assert report["accepted_for_analysis"] is False
    assert report["sample_identity_inferred"] is False
    assert report["replicate_independence_inferred"] is False
    assert report["measurement_semantics_interpreted"] is False
    assert report["ranking_is_scientific_relevance"] is False
    assert report["scientific_support_established"] is False
    assert report["scientific_status_changed"] is False
    assert len(report["triage_sha256"]) == 64

    trace = next(
        item for item in report["member_results"] if item["path"] == "nested/trace.tsv"
    )
    assert trace["structure"]["replicate_independence_inferred"] is False
    assert "time_like" in trace["structure"]["column_profiles"][0][
        "header_semantic_hints_proposal_only"
    ]


def test_archive_mutation_after_prior_inventory_fails_closed(tmp_path):
    archive_path = _archive(tmp_path)
    prior = inspect_zip_archive(archive_path)

    with zipfile.ZipFile(archive_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("later.csv", "x,y\n1,2\n")

    with pytest.raises(ArchiveTabularTriageError, match="differs from prior safe inventory"):
        triage_verified_archive_tables(archive_path, prior)


def test_archive_triage_defers_members_that_exceed_its_read_budget(tmp_path):
    archive_path = _archive(tmp_path, include_large=True)
    prior = inspect_zip_archive(archive_path)

    report = triage_verified_archive_tables(
        archive_path,
        prior,
        max_member_bytes=64,
        max_total_bytes=128,
    )

    assert report["budget_deferred_count"] >= 1
    deferred = {item["path"]: item["reason"] for item in report["budget_deferred_members"]}
    assert deferred["large.csv"] == "triage_member_byte_budget_exceeded"
    assert report["scientific_status_changed"] is False


def test_prior_inventory_must_preserve_no_bulk_extraction_boundary(tmp_path):
    archive_path = _archive(tmp_path)
    prior = inspect_zip_archive(archive_path)
    prior["bulk_extraction_performed"] = True

    with pytest.raises(ArchiveTabularTriageError, match="no-bulk-extraction"):
        triage_verified_archive_tables(archive_path, prior)
