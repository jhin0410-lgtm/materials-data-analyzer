from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from materials_data_analyzer.research_loop.in625_zenodo_episode import (
    run_in625_zenodo_episode,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
)


def _zip_bytes() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("mechanical/tensile.csv", "strain,stress_mpa\n0,0\n0.1,700\n")
        handle.writestr("corrosion/notes.txt", "reported raw data\n")
        handle.writestr("figures/figure.png", b"image-placeholder")
    return stream.getvalue()


def _config() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "episode_id": "in625-zenodo-test",
        "mission_id": "independent-evidence",
        "research_question": "What independent IN625 evidence is available?",
        "objectives": ["acquire evidence", "preserve provenance"],
        "query_aliases": ["Inconel 625 LPBF"],
        "providers": ["zenodo", "crossref"],
        "zenodo": {
            "record_id": 20503603,
            "version_doi": "10.5281/zenodo.20503603",
            "related_article_doi": "10.1016/j.jmrt.2026.05.163",
            "selected_files": [
                "README - Dataset description.txt",
                "Dataset.zip",
            ],
            "archive_file": "Dataset.zip",
        },
        "scientific_boundaries": {
            "issue_76_eligible": False,
            "automatic_scientific_promotion": False,
            "publication_supplement_evidence_class": "E2_publication_supplement",
            "external_validation_requires_sample_acquisition_lineage": True,
            "figure_or_table_values_must_preserve_extraction_route": True,
        },
        "episode_budget": {"max_iterations": 10, "cost_budget": 20.0},
    }


def _metadata(*, license_id: str = "cc-by-4.0") -> tuple[bytes, bytes, bytes]:
    archive = _zip_bytes()
    readme = b"Dataset description\n"
    files = {
        "README - Dataset description.txt": readme,
        "Dataset.zip": archive,
    }
    entries: dict[str, object] = {}
    for key, body in files.items():
        digest = hashlib.md5(body, usedforsecurity=False).hexdigest()
        entries[key] = {
            "key": key,
            "size": len(body),
            "checksum": f"md5:{digest}",
            "links": {
                "content": (
                    "https://zenodo.org/api/records/20503603/files/"
                    + key.replace(" ", "%20")
                    + "/content"
                )
            },
        }
    payload = {
        "id": 20503603,
        "doi": "10.5281/zenodo.20503603",
        "metadata": {
            "title": "Independent LPBF IN625 publication dataset",
            "license": {"id": license_id},
            "related_identifiers": [
                {
                    "identifier": "10.1016/j.jmrt.2026.05.163",
                    "relation": "isSupplementTo",
                }
            ],
        },
        "access": {"record": "public", "files": "public"},
        "files": {"entries": entries},
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8"), readme, archive


def _fake_harvester(*args: object, **kwargs: object) -> dict[str, object]:
    del args, kwargs
    return {
        "schema_version": "1.0",
        "scientific_status_changed": False,
        "catalog_hits_are_scientific_evidence": False,
    }


def test_live_episode_acquires_and_stops_before_scientific_promotion(tmp_path: Path) -> None:
    metadata, readme, archive = _metadata()

    def metadata_fetcher(record_id: str | int) -> tuple[bytes, str]:
        assert int(record_id) == 20503603
        return metadata, "https://zenodo.org/api/records/20503603"

    def content_fetcher(url: str, **kwargs: object) -> FetchResult:
        del kwargs
        body = readme if "README" in url else archive
        return FetchResult(
            body=body,
            status_code=200,
            final_url=url,
            content_type="application/octet-stream",
        )

    output = tmp_path / "live"
    summary = run_in625_zenodo_episode(
        config=_config(),
        output_dir=output,
        metadata_fetcher=metadata_fetcher,
        content_fetcher=content_fetcher,
        harvester=_fake_harvester,
    )
    assert summary["status"] == "acquired_pending_semantic_lineage_and_review_intake"
    assert summary["evidence_class"] == "E2_publication_supplement"
    assert summary["issue_76_eligible"] is False
    assert summary["scientific_hypothesis_verified"] is False
    assert summary["related_article_relation_verified_from_record"] is True
    assert summary["archive_text_hashed_count"] == 2
    episode = json.loads((output / "research_episode.json").read_text(encoding="utf-8"))
    assert episode["state"]["status"] == "blocked"
    assert episode["state"]["evidence_refs"]
    candidate = json.loads(
        (output / "federated_evidence_candidate.json").read_text(encoding="utf-8")
    )
    assert candidate["scientific_status_changed"] is False
    assert candidate["trust_vector"]["sample_identity"] == "unknown"


def test_live_episode_routes_noncommercial_license_to_review_without_download(
    tmp_path: Path,
) -> None:
    metadata, _, _ = _metadata(license_id="cc-by-nc-4.0")

    def metadata_fetcher(_: str | int) -> tuple[bytes, str]:
        return metadata, "https://zenodo.org/api/records/20503603"

    def forbidden_content(*args: object, **kwargs: object) -> FetchResult:
        del args, kwargs
        raise AssertionError("content fetch must not run before review")

    output = tmp_path / "review"
    summary = run_in625_zenodo_episode(
        config=_config(),
        output_dir=output,
        metadata_fetcher=metadata_fetcher,
        content_fetcher=forbidden_content,
        harvester=_fake_harvester,
    )
    assert summary["status"] == "review_required_before_acquisition"
    assert summary["issue_76_eligible"] is False
    episode = json.loads((output / "research_episode.json").read_text(encoding="utf-8"))
    assert episode["state"]["review_queue"]
    assert episode["state"]["status"] == "blocked"


def test_live_episode_network_failure_is_not_negative_scientific_evidence(
    tmp_path: Path,
) -> None:
    def unavailable(_: str | int) -> tuple[bytes, str]:
        raise PublicAcquisitionError("temporary network failure")

    output = tmp_path / "network"
    summary = run_in625_zenodo_episode(
        config=_config(),
        output_dir=output,
        metadata_fetcher=unavailable,
        harvester=_fake_harvester,
    )
    assert summary["status"] == "network_or_provider_unavailable"
    assert summary["scientific_negative_evidence"] is False
    assert summary["scientific_status_changed"] is False
