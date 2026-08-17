from __future__ import annotations

import json

import pytest

from materials_data_analyzer.research_loop.federated_provider_discovery import (
    FederatedProviderDiscoveryError,
    discover_provider,
    federate_discovery_reports,
    normalize_crossref_response,
    normalize_datacite_response,
    normalize_zenodo_response,
    provider_search_url,
)
from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True).encode("utf-8")


def test_datacite_discovery_preserves_dataset_relations_and_rights() -> None:
    payload = {
        "data": [
            {
                "id": "10.5281/zenodo.20503603",
                "attributes": {
                    "doi": "10.5281/zenodo.20503603",
                    "titles": [{"title": "IN625 publication dataset"}],
                    "types": {"resourceTypeGeneral": "Dataset"},
                    "url": "https://zenodo.org/records/20503603",
                    "relatedIdentifiers": [
                        {
                            "relatedIdentifier": "10.1016/j.jmrt.2026.05.163",
                            "relationType": "IsSupplementTo",
                        }
                    ],
                    "rightsList": [
                        {
                            "rightsIdentifier": "cc-by-4.0",
                            "rightsUri": "https://creativecommons.org/licenses/by/4.0/",
                        }
                    ],
                },
            }
        ]
    }
    request_url = provider_search_url("datacite", "inconel 625", limit=5)
    report = normalize_datacite_response(
        response_bytes=_json_bytes(payload),
        request_url=request_url,
        search_phrase="inconel 625",
    )
    candidate = report["candidates"][0]
    assert candidate["persistent_id"] == "10.5281/zenodo.20503603"
    assert candidate["resource_type"] == "Dataset"
    assert "10.1016/j.jmrt.2026.05.163" in candidate["related_identifiers"]
    assert "cc-by-4.0" in candidate["rights"]
    assert candidate["catalog_hit_is_scientific_evidence"] is False
    assert report["catalog_hits_are_scientific_evidence"] is False


def test_crossref_discovery_stays_metadata_only() -> None:
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1016/j.jmrt.2026.05.163",
                    "title": ["LPBF Inconel 625 article"],
                    "type": "journal-article",
                    "URL": "https://doi.org/10.1016/j.jmrt.2026.05.163",
                    "relation": {
                        "is-supplemented-by": [
                            {"id": "10.5281/zenodo.20503603"}
                        ]
                    },
                    "license": [
                        {"URL": "https://creativecommons.org/licenses/by/4.0/"}
                    ],
                }
            ]
        }
    }
    request_url = provider_search_url("crossref", "lpbf inconel 625", limit=3)
    report = normalize_crossref_response(
        response_bytes=_json_bytes(payload),
        request_url=request_url,
        search_phrase="lpbf inconel 625",
    )
    candidate = report["candidates"][0]
    assert candidate["persistent_id"] == "10.1016/j.jmrt.2026.05.163"
    assert candidate["content_route_hint"].startswith("literature_metadata_only")
    assert candidate["requires_source_specific_content_intake"] is True


def test_zenodo_modern_record_preserves_file_count_access_and_relation() -> None:
    payload = {
        "hits": {
            "hits": [
                {
                    "id": 20503603,
                    "doi": "10.5281/zenodo.20503603",
                    "metadata": {
                        "title": "IN625 publication dataset",
                        "resource_type": {"id": "dataset", "title": "Dataset"},
                        "license": {"id": "cc-by-4.0"},
                        "related_identifiers": [
                            {
                                "identifier": "10.1016/j.jmrt.2026.05.163",
                                "relation": "isSupplementTo",
                            }
                        ],
                    },
                    "access": {"record": "public", "files": "public"},
                    "files": {
                        "entries": {
                            "Dataset.zip": {"size": 180700000},
                            "README - Dataset description.txt": {"size": 1400},
                        }
                    },
                    "links": {
                        "self_html": "https://zenodo.org/records/20503603"
                    },
                }
            ]
        }
    }
    request_url = provider_search_url("zenodo", "inconel 625", limit=10)
    report = normalize_zenodo_response(
        response_bytes=_json_bytes(payload),
        request_url=request_url,
        search_phrase="inconel 625",
    )
    candidate = report["candidates"][0]
    assert candidate["content_file_count"] == 2
    assert "cc-by-4.0" in candidate["rights"]
    assert "access:public" in candidate["rights"]
    assert "10.1016/j.jmrt.2026.05.163" in candidate["related_identifiers"]


def test_zenodo_legacy_list_is_supported_without_promoting_content() -> None:
    payload = [
        {
            "id": 123,
            "doi": "10.5281/zenodo.123",
            "metadata": {
                "title": "Legacy record",
                "upload_type": "dataset",
                "license": "cc-by-4.0",
            },
            "files": [{"key": "data.csv", "size": 10}],
            "links": {"html": "https://zenodo.org/records/123"},
        }
    ]
    report = normalize_zenodo_response(
        response_bytes=_json_bytes(payload),
        request_url="https://zenodo.org/api/records?q=legacy&size=1",
        search_phrase="legacy",
    )
    assert report["candidate_count"] == 1
    assert report["candidates"][0]["content_file_count"] == 1
    assert report["catalog_hits_are_scientific_evidence"] is False


def test_duplicate_json_keys_fail_closed() -> None:
    raw = b'{"data": [], "data": []}'
    with pytest.raises(FederatedProviderDiscoveryError, match="duplicate JSON key"):
        normalize_datacite_response(
            response_bytes=raw,
            request_url="https://api.datacite.org/dois?query=x&page%5Bsize%5D=1",
            search_phrase="x",
        )


def test_provider_redirect_may_not_leave_exact_host() -> None:
    payload = _json_bytes({"data": []})

    def fake_fetcher(*args: object, **kwargs: object) -> FetchResult:
        del args, kwargs
        return FetchResult(
            body=payload,
            status_code=200,
            final_url="https://evil.example/dois?query=x",
            content_type="application/json",
        )

    with pytest.raises(FederatedProviderDiscoveryError, match="exact HTTPS host"):
        discover_provider("datacite", "x", fetcher=fake_fetcher, limit=1)


def test_provider_limit_is_bounded() -> None:
    with pytest.raises(FederatedProviderDiscoveryError, match="between 1 and"):
        provider_search_url("zenodo", "x", limit=26)


def test_discover_provider_uses_exact_response_bytes() -> None:
    payload = _json_bytes({"message": {"items": []}})

    def fake_fetcher(url: str, **kwargs: object) -> FetchResult:
        del kwargs
        return FetchResult(
            body=payload,
            status_code=200,
            final_url=url,
            content_type="application/json",
        )

    report = discover_provider(
        "crossref",
        {"material": "IN625", "process": "LPBF"},
        fetcher=fake_fetcher,
        limit=2,
    )
    assert report["provider"] == "crossref"
    assert report["response_sha256"]
    assert report["candidate_count"] == 0


def test_federation_deduplicates_doi_without_claiming_independence() -> None:
    datacite_payload = {
        "data": [
            {
                "id": "10.5281/zenodo.20503603",
                "attributes": {
                    "doi": "10.5281/zenodo.20503603",
                    "titles": [{"title": "Dataset via DataCite"}],
                    "types": {"resourceTypeGeneral": "Dataset"},
                    "url": "https://zenodo.org/records/20503603",
                    "relatedIdentifiers": [],
                    "rightsList": [],
                },
            }
        ]
    }
    zenodo_payload = {
        "hits": {
            "hits": [
                {
                    "id": 20503603,
                    "doi": "10.5281/zenodo.20503603",
                    "metadata": {"title": "Dataset via Zenodo"},
                    "links": {
                        "self_html": "https://zenodo.org/records/20503603"
                    },
                }
            ]
        }
    }
    datacite = normalize_datacite_response(
        response_bytes=_json_bytes(datacite_payload),
        request_url=provider_search_url("datacite", "in625", limit=1),
        search_phrase="in625",
    )
    zenodo = normalize_zenodo_response(
        response_bytes=_json_bytes(zenodo_payload),
        request_url=provider_search_url("zenodo", "in625", limit=1),
        search_phrase="in625",
    )
    federated = federate_discovery_reports([datacite, zenodo])
    assert federated["record_count"] == 1
    record = federated["records"][0]
    assert record["identity"] == "doi:10.5281/zenodo.20503603"
    assert record["providers"] == ["datacite", "zenodo"]
    assert federated["deduplication_does_not_establish_source_independence"] is True
