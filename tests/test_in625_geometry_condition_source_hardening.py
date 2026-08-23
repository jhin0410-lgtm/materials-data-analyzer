from __future__ import annotations

from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition as acquisition,
)


def test_claim_anchor_cannot_span_beyond_local_context_window() -> None:
    claim = {
        "claim_id": "bounded-context",
        "anchor_regex": "alpha.*omega",
        "scope": "test",
    }
    receipt = acquisition._claim_receipt(
        claim,
        ["alpha " + ("x" * (acquisition.MAX_CLAIM_MATCH_UTF8_BYTES + 32)) + " omega"],
        is_pdf=False,
    )
    assert receipt["matched"] is False
    assert receipt["match_count"] == 0
    assert receipt["matching_policy"] == {
        "wildcard_span_bounded": True,
        "max_matched_text_utf8_bytes": acquisition.MAX_CLAIM_MATCH_UTF8_BYTES,
    }


def test_claim_anchor_accepts_same_semantics_inside_local_context() -> None:
    claim = {
        "claim_id": "bounded-context",
        "anchor_regex": "alpha.*omega",
        "scope": "test",
    }
    receipt = acquisition._claim_receipt(
        claim,
        ["prefix alpha nearby omega suffix"],
        is_pdf=False,
    )
    assert receipt["matched"] is True
    assert receipt["match_count"] == 1
    assert receipt["matches"][0]["matched_text_utf8_bytes"] < 64


def test_html_script_or_style_text_cannot_satisfy_claim_anchor() -> None:
    pages = acquisition._html_pages(
        b"<html><script>forged alpha omega</script><style>alpha omega</style>"
        b"<body>visible scientific text</body></html>"
    )
    receipt = acquisition._claim_receipt(
        {
            "claim_id": "visible-only",
            "anchor_regex": "alpha.*omega",
            "scope": "test",
        },
        pages,
        is_pdf=False,
    )
    assert receipt["matched"] is False


def _qualification(*, max_source_bytes: int, max_total_bytes: int) -> dict[str, Any]:
    return {
        "qualification_status": "exact_multisource_condition_evidence_policy_authenticated",
        "policy_id": acquisition.POLICY_ID,
        "action_class": acquisition.ACTION_CLASS,
        "source_count": acquisition.MAX_REQUESTS,
        "allowed_hosts": list(acquisition.ALLOWED_HOSTS),
        "max_requests": acquisition.MAX_REQUESTS,
        "max_source_bytes": max_source_bytes,
        "max_total_bytes": max_total_bytes,
        "network_access_performed": False,
        "policy_sha256": "a" * 64,
        "registry_git_blob_sha1": "b" * 40,
    }


def _registry() -> dict[str, Any]:
    return {
        "sources": [
            {
                "source_id": f"source-{index}",
                "url": "https://www.nist.gov/test",
                "media_type": "html",
                "source_class": "official_web_document",
                "authority": "NIST",
                "title": f"Source {index}",
                "claims_under_review": [
                    {
                        "claim_id": f"claim-{index}",
                        "anchor_regex": "a.*b",
                        "scope": "test",
                    }
                ],
            }
            for index in range(acquisition.MAX_REQUESTS)
        ]
    }


def test_each_fetch_is_limited_by_remaining_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition, "MAX_SOURCE_BYTES", 10)
    monkeypatch.setattr(acquisition, "MAX_TOTAL_BYTES", 20)
    requested_budgets: list[int] = []

    def fetcher(
        url: str,
        *,
        allowed_hosts: object,
        max_bytes: int,
        timeout_seconds: float,
    ) -> acquisition.FetchResult:
        del url, allowed_hosts, timeout_seconds
        requested_budgets.append(max_bytes)
        return acquisition.FetchResult(
            body=b"a b",
            final_url="https://www.nist.gov/test",
            status_code=200,
            content_type="text/html",
        )

    with pytest.raises(
        acquisition.GeometryConditionSourceAcquisitionError,
        match="beyond current remaining budget",
    ):
        acquisition.acquire_geometry_condition_sources(
            qualification=_qualification(max_source_bytes=10, max_total_bytes=20),
            source_registry=_registry(),
            fetcher=fetcher,
        )

    assert requested_budgets == [10, 10, 10, 10, 8, 5, 2]


def test_acquisition_report_records_pdf_extractor_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition, "MAX_SOURCE_BYTES", 32)
    monkeypatch.setattr(acquisition, "MAX_TOTAL_BYTES", 256)

    def fetcher(
        url: str,
        *,
        allowed_hosts: object,
        max_bytes: int,
        timeout_seconds: float,
    ) -> acquisition.FetchResult:
        del url, allowed_hosts, max_bytes, timeout_seconds
        return acquisition.FetchResult(
            body=b"a b",
            final_url="https://www.nist.gov/test",
            status_code=200,
            content_type="text/html",
        )

    result = acquisition.acquire_geometry_condition_sources(
        qualification=_qualification(max_source_bytes=32, max_total_bytes=256),
        source_registry=_registry(),
        fetcher=fetcher,
    )
    assert result["pdf_extractor"]["package"] == "pypdf"
    assert isinstance(result["pdf_extractor"]["version"], str)
    assert result["pdf_extractor"]["version"]
    assert result["pdf_extractor"]["strict"] is False
    assert result["claim_matching_policy"]["max_matched_text_utf8_bytes"] == 4096
