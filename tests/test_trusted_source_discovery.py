import json

import pytest

from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult
from materials_data_analyzer.research_loop.trusted_source_discovery import (
    AUTO,
    REVIEW_REQUIRED,
    TrustedSourceDiscoveryError,
    build_evidence_search_phrase,
    discover_nist_rmm,
    nist_rmm_search_endpoint,
    normalize_nist_rmm_search_response,
    trusted_provider_authorization,
)


def _response(*records):
    return json.dumps(
        {"ResultCount": len(records), "PageSize": len(records), "ResultData": list(records)},
        sort_keys=True,
    ).encode()


def test_nist_rmm_public_record_is_policy_discoverable_without_human_approval():
    payload = _response(
        {
            "@id": "ark:/88434/mds2-2923",
            "ediid": "mds2-2923",
            "@type": ["nrdp:PublicDataResource"],
            "accessLevel": "public",
            "title": "Single-track laser scans on IN625",
            "description": "melt pool width measurements",
        }
    )

    def fetcher(url, **kwargs):
        assert kwargs["allowed_hosts"] == ["data.nist.gov"]
        return FetchResult(payload, 200, url, "application/json")

    report = discover_nist_rmm(
        {"material": "IN625", "measurement": "melt pool width"},
        fetcher=fetcher,
    )

    assert report["candidates"][0]["product_id"] == "mds2-2923"
    assert report["candidates"][0]["discovery_decision"] == AUTO
    assert report["candidates"][0]["scientific_status_changed"] is False
    assert report["network_failure_is_scientific_negative_evidence"] is False
    assert trusted_provider_authorization("nist_rmm")["human_approval_required"] is False


def test_public_status_ambiguity_routes_record_to_review_not_auto():
    phrase = "IN625 melt pool"
    url = nist_rmm_search_endpoint(phrase)
    report = normalize_nist_rmm_search_response(
        response_bytes=_response(
            {
                "@id": "ark:/88434/mds2-2923",
                "ediid": "mds2-2923",
                "title": "IN625 melt pool data",
            }
        ),
        search_phrase=phrase,
        request_url=url,
    )
    candidate = report["candidates"][0]
    assert candidate["discovery_decision"] == REVIEW_REQUIRED
    assert candidate["scientific_status_changed"] is False


def test_unknown_provider_never_inherits_nist_auto_authorization():
    decision = trusted_provider_authorization("arbitrary_web")
    assert decision["decision"] == REVIEW_REQUIRED
    assert decision["human_approval_required"] is True


def test_rmm_schema_and_endpoint_fail_closed():
    with pytest.raises(TrustedSourceDiscoveryError, match="ResultData"):
        normalize_nist_rmm_search_response(
            response_bytes=b'{"ResultCount": 1}',
            search_phrase="IN625",
            request_url="https://data.nist.gov/rmm/records?searchphrase=IN625",
        )
    with pytest.raises(TrustedSourceDiscoveryError, match="outside exact NIST RMM"):
        normalize_nist_rmm_search_response(
            response_bytes=_response(),
            search_phrase="IN625",
            request_url="https://example.com/rmm/records?searchphrase=IN625",
        )


def test_evidence_gap_query_is_deterministic_and_bounded():
    first = build_evidence_search_phrase(
        {
            "material": "IN625 IN625",
            "process": "laser powder bed fusion",
            "measurement": "melt pool width",
        }
    )
    second = build_evidence_search_phrase(
        {
            "material": "IN625 IN625",
            "process": "laser powder bed fusion",
            "measurement": "melt pool width",
        }
    )
    assert first == second
    assert first.split().count("in625") == 1
