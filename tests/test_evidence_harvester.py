from __future__ import annotations

from materials_data_analyzer.research_loop.evidence_harvester import (
    expand_search_phrases,
    harvest_evidence,
)
from materials_data_analyzer.research_loop.kernel import ResearchLoopError


def _nist_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "provider": "nist_rmm",
        "request_url": "https://data.nist.gov/rmm/records?searchphrase=in625",
        "search_phrase": "in625",
        "query_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "reported_result_count": 1,
        "returned_result_count": 1,
        "candidates": [
            {
                "candidate_id": "nist-rmm:mds2-2923",
                "provider": "nist_rmm",
                "product_id": "mds2-2923",
            }
        ],
        "network_failure_is_scientific_negative_evidence": False,
    }


def _catalog(provider: str, doi: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "provider": provider,
        "request_url": f"https://example.invalid/{provider}",
        "search_phrase": "in625",
        "query_sha256": "c" * 64,
        "response_sha256": ("d" if provider == "datacite" else "e") * 64,
        "candidate_count": 1,
        "candidates": [
            {
                "candidate_id": f"{provider}:candidate",
                "provider": provider,
                "persistent_id": doi,
                "title": "Dataset",
                "resource_type": "Dataset",
                "landing_url": "https://zenodo.org/records/20503603",
                "related_identifiers": [],
                "rights": [],
                "content_file_count": 2 if provider == "zenodo" else None,
                "content_route_hint": "route",
                "provider_record_sha256": ("1" if provider == "datacite" else "2") * 64,
                "catalog_hit_is_scientific_evidence": False,
                "requires_source_specific_content_intake": True,
                "scientific_status_changed": False,
            }
        ],
        "catalog_hits_are_scientific_evidence": False,
        "network_failure_is_scientific_negative_evidence": False,
    }


def test_query_aliases_expand_without_duplicate_searches() -> None:
    phrases = expand_search_phrases(
        {"material": "IN625", "process": "LPBF"},
        query_aliases=["Inconel 625 laser powder bed fusion", "IN625 LPBF"],
    )
    assert phrases[0] == "in625 lpbf"
    assert "inconel 625 laser powder bed fusion" in phrases
    assert phrases.count("in625 lpbf") == 1


def test_harvester_continues_when_one_provider_fails() -> None:
    class ExpectedFailure(ResearchLoopError):
        pass

    def failing(_: object) -> dict[str, object]:
        raise ExpectedFailure("temporary provider failure")

    report = harvest_evidence(
        "IN625 LPBF",
        providers=["nist_rmm", "datacite"],
        discoverers={
            "nist_rmm": lambda _: _nist_report(),
            "datacite": failing,
        },
    )
    assert report["successful_search_count"] == 1
    assert report["failed_search_count"] == 1
    assert report["failures"][0]["scientific_negative_evidence"] is False
    assert report["provider_failure_is_scientific_negative_evidence"] is False
    assert any(
        item["action_type"] == "nist_pdr_metadata_resolution"
        for item in report["action_queue"]
    )


def test_harvester_federates_same_doi_and_prefers_zenodo_content_resolution() -> None:
    doi = "10.5281/zenodo.20503603"
    report = harvest_evidence(
        "IN625",
        providers=["datacite", "zenodo"],
        discoverers={
            "datacite": lambda _: _catalog("datacite", doi),
            "zenodo": lambda _: _catalog("zenodo", doi),
        },
    )
    assert report["federated_catalog"]["record_count"] == 1
    record = report["federated_catalog"]["records"][0]
    assert record["providers"] == ["datacite", "zenodo"]
    actions = report["action_queue"]
    assert len(actions) == 1
    assert actions[0]["action_type"] == "zenodo_record_metadata_resolution"
    assert report["catalog_hits_are_scientific_evidence"] is False


def test_empty_catalog_is_not_negative_scientific_evidence() -> None:
    empty = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "provider": "crossref",
        "request_url": "https://api.crossref.org/works?q=x",
        "search_phrase": "x",
        "query_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "candidate_count": 0,
        "candidates": [],
        "catalog_hits_are_scientific_evidence": False,
        "network_failure_is_scientific_negative_evidence": False,
    }
    report = harvest_evidence(
        "x",
        providers=["crossref"],
        discoverers={"crossref": lambda _: empty},
    )
    assert report["action_queue"] == []
    assert report["empty_search_is_scientific_negative_evidence"] is False
