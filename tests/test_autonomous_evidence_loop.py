import hashlib
import json
from pathlib import Path

from materials_data_analyzer.research_loop.autonomous_evidence_loop import (
    ACQUISITION_BLOCKED,
    INSUFFICIENT_EVIDENCE,
    SUPPORTED,
    run_autonomous_evidence_loop,
    select_nist_artifacts_for_gap,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
)


def _fixture_transport():
    workbook = b"fixture-xlsx-bytes"
    readme = b"fixture readme"
    metadata = json.dumps(
        {
            "@id": "ark:/88434/mds2-2923",
            "ediid": "mds2-2923",
            "accessLevel": "public",
            "version": "1.0",
            "components": [
                {
                    "@type": ["nrdp:DataFile"],
                    "filepath": "Master_TrackList_Measurements.xlsx",
                    "downloadURL": "https://data.nist.gov/od/ds/mds2-2923/Master_TrackList_Measurements.xlsx",
                    "size": len(workbook),
                    "checksum": {
                        "hash": hashlib.sha256(workbook).hexdigest(),
                        "algorithm": {"tag": "sha256"},
                    },
                },
                {
                    "@type": ["nrdp:DataFile"],
                    "filepath": "2923_README.txt",
                    "downloadURL": "https://data.nist.gov/od/ds/mds2-2923/2923_README.txt",
                    "size": len(readme),
                    "checksum": {
                        "hash": hashlib.sha256(readme).hexdigest(),
                        "algorithm": {"tag": "sha256"},
                    },
                },
            ],
        },
        sort_keys=True,
    ).encode()
    discovery = json.dumps(
        {
            "ResultCount": 1,
            "PageSize": 1,
            "ResultData": [
                {
                    "@id": "ark:/88434/mds2-2923",
                    "ediid": "mds2-2923",
                    "@type": ["nrdp:PublicDataResource"],
                    "accessLevel": "public",
                    "title": "IN625 single-track melt pool measurements",
                    "description": "laser powder bed fusion melt pool width",
                }
            ],
        },
        sort_keys=True,
    ).encode()

    def fetcher(url, **kwargs):
        if url.startswith("https://data.nist.gov/rmm/records?"):
            return FetchResult(discovery, 200, url, "application/json")
        if url == "https://data.nist.gov/od/id/mds2-2923":
            return FetchResult(metadata, 200, url, "application/json")
        if url.endswith("Master_TrackList_Measurements.xlsx"):
            return FetchResult(workbook, 200, url, "application/octet-stream")
        if url.endswith("2923_README.txt"):
            return FetchResult(readme, 200, url, "text/plain")
        raise AssertionError(f"unexpected URL {url}")

    return fetcher


def test_bounded_selector_prefers_measurement_table_over_unrelated_image():
    candidates = [
        {"artifact_path": "raw/large_micrograph.tif"},
        {"artifact_path": "Master_TrackList_Measurements.xlsx"},
        {"artifact_path": "README.txt"},
    ]
    selected = select_nist_artifacts_for_gap(
        candidates,
        evidence_gap={"material": "IN625", "measurement": "melt pool measurements"},
        max_files=2,
    )
    paths = [item["artifact_path"] for item in selected]
    assert paths[0] == "Master_TrackList_Measurements.xlsx"
    assert "raw/large_micrograph.tif" not in paths


def test_default_loop_acquires_exact_bytes_but_stops_before_scientific_promotion(tmp_path):
    result = run_autonomous_evidence_loop(
        {"material": "IN625", "measurement": "melt pool measurements"},
        output_root=tmp_path,
        fetcher=_fixture_transport(),
        max_iterations=2,
        max_records_per_iteration=1,
        max_files_per_product=2,
    )
    assert result["terminal_status"] == INSUFFICIENT_EVIDENCE
    assert result["stop_reason"] == "scientific_intake_not_satisfied"
    assert result["history"][0]["accepted_intake_count"] == 0
    assert result["history"][0]["scientific_status_changed"] is False
    assert list(Path(tmp_path).rglob("acquisition_receipt.json"))


def test_registered_intake_and_analysis_can_close_the_loop_without_per_file_approval(tmp_path):
    def intake_handler(**kwargs):
        receipt = kwargs["receipt"]
        return {
            "accepted_for_analysis": True,
            "scientific_status_changed": True,
            "artifact_sha256": receipt["artifact_sha256"],
            "domain": "fixture_in625",
        }

    def analysis_handler(**kwargs):
        assert kwargs["accepted_intakes"]
        return {
            "scientific_outcome": SUPPORTED,
            "evidence_gap_resolved": True,
            "basis": "fixture-domain-analysis",
        }

    result = run_autonomous_evidence_loop(
        {"material": "IN625", "measurement": "melt pool measurements"},
        output_root=tmp_path,
        fetcher=_fixture_transport(),
        intake_handler=intake_handler,
        analysis_handler=analysis_handler,
        max_records_per_iteration=1,
        max_files_per_product=1,
    )
    assert result["terminal_status"] == SUPPORTED
    assert result["iterations_completed"] == 1
    assert result["review_queue"] == []
    assert result["physical_experiment_execution_authorized"] is False


def test_network_failure_is_operational_block_not_scientific_contradiction(tmp_path):
    def broken_fetcher(url, **kwargs):
        raise PublicAcquisitionError("offline")

    result = run_autonomous_evidence_loop(
        "IN625 independent measurements",
        output_root=tmp_path,
        fetcher=broken_fetcher,
    )
    assert result["terminal_status"] == ACQUISITION_BLOCKED
    assert result["network_failure_is_scientific_negative_evidence"] is False
    assert result["history"][0]["scientific_status_changed"] is False
