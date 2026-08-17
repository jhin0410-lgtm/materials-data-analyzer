from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.nist_pdr_acquisition import (
    NistPdrAcquisitionError,
    acquire_nist_pdr_file,
    discover_nist_pdr_candidates,
    nist_pdr_metadata_endpoint,
    plan_nist_pdr_product_acquisition,
)
from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult


def _metadata(artifact: bytes) -> bytes:
    payload = {
        "@id": "ark:/88434/mds2-2923",
        "@type": ["nrdp:DataPublication", "nrdp:PublicDataResource"],
        "version": "1.0",
        "components": [
            {
                "@type": ["nrdp:DataFile", "nrdp:DownloadableFile"],
                "filepath": "Master_TrackList_Measurements.xlsx",
                "downloadURL": (
                    "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
                    "Master_TrackList_Measurements.xlsx"
                ),
                "size": len(artifact),
                "checksum": {
                    "hash": hashlib.sha256(artifact).hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            },
            {
                "@type": ["nrdp:DataFile", "nrdp:DownloadableFile"],
                "filepath": "2923_README.txt",
                "downloadURL": (
                    "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
                    "2923_README.txt"
                ),
                "size": 6,
                "checksum": {
                    "hash": hashlib.sha256(b"readme").hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            },
        ],
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def test_nerdm_component_is_checksum_bound_auto_candidate() -> None:
    artifact = b"xlsx-row-level-bytes"
    metadata = _metadata(artifact)

    candidate = discover_nist_pdr_candidates(
        metadata_bytes=metadata,
        product_id="mds2-2923",
        filepaths=["Master_TrackList_Measurements.xlsx"],
    )[0]

    assert nist_pdr_metadata_endpoint("mds2-2923") == (
        "https://data.nist.gov/od/id/mds2-2923"
    )
    assert candidate["source_version"] == "1.0"
    assert candidate["metadata_sha256"] == hashlib.sha256(metadata).hexdigest()
    assert candidate["expected_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert candidate["expected_size_bytes"] == len(artifact)
    assert candidate["access"]["authentication_required"] is False


def test_product_plan_does_not_require_per_file_approval() -> None:
    artifact = b"xlsx-row-level-bytes"
    queue = plan_nist_pdr_product_acquisition(
        product_id="mds2-2923",
        metadata_bytes=_metadata(artifact),
    )

    assert queue["candidate_count"] == 2
    assert queue["auto_count"] == 2
    assert queue["review_required_count"] == 0
    assert queue["blocked_count"] == 0


def test_non_sha256_component_is_rejected() -> None:
    artifact = b"xlsx-row-level-bytes"
    payload = json.loads(_metadata(artifact))
    payload["components"][0]["checksum"]["algorithm"]["tag"] = "md5"

    with pytest.raises(NistPdrAcquisitionError, match="not explicitly SHA-256"):
        discover_nist_pdr_candidates(
            metadata_bytes=(json.dumps(payload) + "\n").encode("utf-8"),
            product_id="mds2-2923",
            filepaths=["Master_TrackList_Measurements.xlsx"],
        )


def test_duplicate_downloadable_filepath_is_rejected() -> None:
    artifact = b"xlsx-row-level-bytes"
    payload = json.loads(_metadata(artifact))
    payload["components"].append(dict(payload["components"][0]))

    with pytest.raises(NistPdrAcquisitionError, match="duplicate downloadable filepath"):
        discover_nist_pdr_candidates(
            metadata_bytes=(json.dumps(payload) + "\n").encode("utf-8"),
            product_id="mds2-2923",
            filepaths=["Master_TrackList_Measurements.xlsx"],
        )


def test_live_path_fetches_metadata_then_exact_artifact(tmp_path: Path) -> None:
    artifact = b"xlsx-row-level-bytes"
    metadata = _metadata(artifact)
    metadata_url = "https://data.nist.gov/od/id/mds2-2923"
    artifact_url = (
        "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
        "Master_TrackList_Measurements.xlsx"
    )
    calls: list[str] = []

    def fake_fetcher(
        url: str,
        *,
        allowed_hosts: list[str],
        max_bytes: int,
        timeout_seconds: float,
        headers: dict[str, str],
    ) -> FetchResult:
        assert allowed_hosts == ["data.nist.gov"]
        calls.append(url)
        if url == metadata_url:
            assert headers["Accept"] == "application/json"
            return FetchResult(metadata, 200, url, "application/json")
        if url == artifact_url:
            assert headers["Accept"] == "*/*"
            assert max_bytes == len(artifact) + 1
            return FetchResult(artifact, 200, url, "application/octet-stream")
        raise AssertionError(url)

    output = tmp_path / "mds2-2923-workbook"
    receipt = acquire_nist_pdr_file(
        product_id="mds2-2923",
        filepath="Master_TrackList_Measurements.xlsx",
        output_dir=output,
        fetcher=fake_fetcher,
    )

    assert calls == [metadata_url, artifact_url]
    assert receipt["recorded_acquisition_provenance_authenticated"] is True
    assert receipt["requires_scientific_intake"] is True
    assert (output / "Master_TrackList_Measurements.xlsx").read_bytes() == artifact


def test_missing_requested_file_is_not_inferred() -> None:
    artifact = b"xlsx-row-level-bytes"

    with pytest.raises(NistPdrAcquisitionError, match="not downloadable"):
        discover_nist_pdr_candidates(
            metadata_bytes=_metadata(artifact),
            product_id="mds2-2923",
            filepaths=["missing.xlsx"],
        )
