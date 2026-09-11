from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from materials_data_analyzer.research_loop import autonomous_production_driver as driver
from materials_data_analyzer.research_loop import (
    in625_archive_network_acquisition as archive,
)
from materials_data_analyzer.research_loop import in625_zenodo_live_evidence as live
from materials_data_analyzer.research_loop import public_data_acquisition as public
from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs/research/in625_zenodo_20503603_verified_source.v1.json"
RECORD_URL = "https://zenodo.org/api/records/20503603"
README_NAME = "README - Dataset description.txt"
README_URL = "https://zenodo.org/api/records/20503603/files/README%20-%20Dataset%20description.txt/content"
ARCHIVE_URL = "https://zenodo.org/api/records/20503603/files/Dataset.zip/content"


def _metadata(*, archive_url: str = ARCHIVE_URL, readme_url: str = README_URL) -> tuple[dict[str, object], bytes]:
    config = json.loads(SOURCE.read_text(encoding="utf-8"))
    zenodo = config["zenodo"]
    files = zenodo["files"]
    value = {
        "id": zenodo["record_id"],
        "doi": zenodo["version_doi"],
        "metadata": {
            "title": zenodo["expected_title"],
            "publication_date": zenodo["publication_date"],
            "access_right": "open",
            "license": {"id": zenodo["license_id"]},
            "related_identifiers": [{"identifier": zenodo["related_article_doi"], "relation": zenodo["related_article_relation"], "scheme": "doi"}],
        },
        "files": [
            {"key": README_NAME, "size": files[README_NAME]["size_bytes"], "checksum": f"{files[README_NAME]['provider_checksum_algorithm']}:{files[README_NAME]['provider_checksum_digest']}", "links": {"self": readme_url}},
            {"key": "Dataset.zip", "size": files["Dataset.zip"]["size_bytes"], "checksum": f"{files['Dataset.zip']['provider_checksum_algorithm']}:{files['Dataset.zip']['provider_checksum_digest']}", "links": {"self": archive_url}},
        ],
    }
    return config, json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@pytest.mark.parametrize("bad_url", ["https://zenodo.org/api/records/20503603/files/other.zip/content", f"{ARCHIVE_URL}?download=1", "https://zenodo.org/api/users/me"])
def test_metadata_rejects_same_host_archive_authority_widening(bad_url: str) -> None:
    config, metadata = _metadata(archive_url=bad_url)
    with pytest.raises(live.In625ZenodoLiveEvidenceError, match="published-record file content route"):
        live.validate_verified_in625_zenodo_metadata(config=config, metadata_bytes=metadata)


def test_metadata_rejects_same_host_readme_query_widening() -> None:
    config, metadata = _metadata(readme_url=f"{README_URL}?x=1")
    with pytest.raises(live.In625ZenodoLiveEvidenceError, match="published-record file content route"):
        live.validate_verified_in625_zenodo_metadata(config=config, metadata_bytes=metadata)


def test_archive_low_level_fetch_rejects_non_archive_same_host_route_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False
    def forbidden(*args: object, **kwargs: object) -> FetchResult:
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")
    monkeypatch.setattr(archive, "fetch_https_bytes", forbidden)
    with pytest.raises(archive.In625ArchiveNetworkAcquisitionError, match="authorized archive content route"):
        archive.fetch_authorized_zenodo_bytes("https://zenodo.org/api/users/me", max_bytes=10)
    assert called is False


def test_archive_fetch_passes_exact_url_to_shared_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    def fake(url: str, **kwargs: object) -> FetchResult:
        observed["url"] = url
        observed.update(kwargs)
        return FetchResult(b"x", 200, url, "application/zip")
    monkeypatch.setattr(archive, "fetch_https_bytes", fake)
    result = archive.fetch_authorized_zenodo_bytes(ARCHIVE_URL, max_bytes=10)
    assert result.body == b"x"
    assert observed["exact_url"] == ARCHIVE_URL


def test_shared_exact_url_rejects_initial_mismatch_before_network() -> None:
    with pytest.raises(public.PublicAcquisitionError, match="differs from the exact authorized"):
        public.fetch_https_bytes(RECORD_URL, allowed_hosts=["zenodo.org"], max_bytes=10, exact_url=f"{RECORD_URL}?x=1")


def test_shared_exact_url_rejects_same_host_redirect_before_follow() -> None:
    handler = public._RestrictedRedirectHandler(["zenodo.org"], exact_url=ARCHIVE_URL)
    with pytest.raises(public.PublicAcquisitionError, match="redirect endpoint left"):
        handler.redirect_request(Request(ARCHIVE_URL), None, 302, "Found", {}, "https://zenodo.org/api/users/me")


def test_driver_exact_get_passes_exact_url_to_shared_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}
    def fake(url: str, **kwargs: object) -> FetchResult:
        observed["url"] = url
        observed.update(kwargs)
        return FetchResult(b"{}", 200, url, "application/json")
    monkeypatch.setattr(driver, "fetch_https_bytes", fake)
    assert driver._exact_zenodo_get(RECORD_URL, expected_path="/api/records/20503603") == b"{}"
    assert observed["exact_url"] == RECORD_URL


def test_driver_json_snapshot_rejects_duplicate_keys() -> None:
    with pytest.raises(driver.AutonomousProductionDriverError, match="duplicate JSON key"):
        driver._read_json_bytes(b'{"source_id":"a","source_id":"b"}', "source")
