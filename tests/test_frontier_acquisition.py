from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.frontier_acquisition import (
    FrontierAcquisitionError,
    acquire_frontier_candidate,
    load_frontier_acquisition_plan,
)
from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult


def _metadata(readme: bytes, workbook: bytes) -> bytes:
    payload = {
        "@id": "ark:/88434/mds2-2923",
        "@type": ["nrdp:DataPublication", "nrdp:PublicDataResource"],
        "version": "1.0",
        "components": [
            {
                "@type": ["nrdp:DataFile", "nrdp:DownloadableFile"],
                "filepath": "2923_README.txt",
                "downloadURL": (
                    "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
                    "2923_README.txt"
                ),
                "size": len(readme),
                "checksum": {
                    "hash": hashlib.sha256(readme).hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            },
            {
                "@type": ["nrdp:DataFile", "nrdp:DownloadableFile"],
                "filepath": "Master_TrackList_Measurements.xlsx",
                "downloadURL": (
                    "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
                    "Master_TrackList_Measurements.xlsx"
                ),
                "size": len(workbook),
                "checksum": {
                    "hash": hashlib.sha256(workbook).hexdigest(),
                    "algorithm": {"tag": "sha256"},
                },
            },
        ],
    }
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def _frontier(path: Path, *, machine_actionable: bool = True) -> None:
    candidate: dict[str, object] = {
        "candidate_id": "nist-mds2-2923-cross-sectional-micrographs",
        "issue_76_eligible": False,
    }
    if machine_actionable:
        candidate["automatic_acquisition_plan"] = {
            "adapter": "nist_pdr",
            "product_id": "mds2-2923",
            "filepaths": [
                "2923_README.txt",
                "Master_TrackList_Measurements.xlsx",
            ],
            "approval_mode": "automatic_when_public_checksum_bound_policy_passes",
            "human_review_is_exception_only": True,
        }
    path.write_text(
        json.dumps({"schema_version": "1.0", "candidates": [candidate]}),
        encoding="utf-8",
    )


def test_frontier_plan_requires_only_scientific_candidate_id(tmp_path: Path) -> None:
    path = tmp_path / "frontier.json"
    _frontier(path)

    plan = load_frontier_acquisition_plan(
        path, "nist-mds2-2923-cross-sectional-micrographs"
    )

    assert plan["adapter"] == "nist_pdr"
    assert plan["product_id"] == "mds2-2923"
    assert plan["filepaths"] == [
        "2923_README.txt",
        "Master_TrackList_Measurements.xlsx",
    ]
    assert plan["human_review_is_exception_only"] is True


def test_discovery_only_candidate_cannot_silently_execute(tmp_path: Path) -> None:
    path = tmp_path / "frontier.json"
    _frontier(path, machine_actionable=False)

    with pytest.raises(FrontierAcquisitionError, match="discovery-only"):
        load_frontier_acquisition_plan(
            path, "nist-mds2-2923-cross-sectional-micrographs"
        )


def test_frontier_candidate_runs_metadata_and_two_files_without_per_file_approval(
    tmp_path: Path,
) -> None:
    frontier = tmp_path / "frontier.json"
    _frontier(frontier)
    readme = b"authoritative readme"
    workbook = b"authoritative workbook bytes"
    metadata = _metadata(readme, workbook)
    metadata_url = "https://data.nist.gov/od/id/mds2-2923"
    bodies = {
        metadata_url: metadata,
        (
            "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
            "2923_README.txt"
        ): readme,
        (
            "https://data.nist.gov/od/ds/ark:/88434/mds2-2923/"
            "Master_TrackList_Measurements.xlsx"
        ): workbook,
    }
    calls: list[str] = []

    def fake_fetcher(url: str, **_: object) -> FetchResult:
        calls.append(url)
        return FetchResult(bodies[url], 200, url)

    report = acquire_frontier_candidate(
        frontier_path=frontier,
        candidate_id="nist-mds2-2923-cross-sectional-micrographs",
        output_root=tmp_path / "acquired",
        fetcher=fake_fetcher,
    )

    assert calls[0] == metadata_url
    assert set(calls[1:]) == set(bodies) - {metadata_url}
    acquisition = report["acquisition"]
    assert acquisition["automatic_execution_attempted"] == 2
    assert acquisition["automatic_execution_succeeded"] == 2
    assert acquisition["automatic_execution_failed"] == 0
    assert acquisition["human_review_required"] == []
    assert report["scientific_status_changed"] is False
    assert report["requires_scientific_intake"] is True
