"""Provider-bounded literature metadata discovery and evidence normalization.

This module builds exact public metadata requests for Crossref, DataCite, and NCBI PMC.
It intentionally does not turn metadata hits into scientific evidence or grant reuse rights.
Fetched records must still pass source policy, rights, semantic, lineage, and scientific
intake gates.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode, urlsplit

from .evidence_federation import (
    EvidenceClass,
    EvidenceTrustVector,
    FederatedEvidenceCandidate,
)
from .kernel import ResearchLoopError

LITERATURE_HARVESTER_POLICY_VERSION = "1.0"
_PROVIDER_ENDPOINTS = {
    "crossref": "https://api.crossref.org/works",
    "datacite": "https://api.datacite.org/dois",
    "pmc": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
}


class LiteratureEvidenceHarvesterError(ResearchLoopError):
    """Raised when literature metadata cannot be handled without unsafe inference."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiteratureEvidenceHarvesterError(f"{field} must be non-empty text")
    return value.strip()


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_literature_discovery_request(
    *,
    provider: str,
    query: str,
    rows: int = 20,
) -> dict[str, Any]:
    provider_id = _text(provider, "provider").lower()
    if provider_id not in _PROVIDER_ENDPOINTS:
        raise LiteratureEvidenceHarvesterError("unsupported literature provider")
    query_text = _text(query, "query")
    if len(query_text) > 512:
        raise LiteratureEvidenceHarvesterError("query exceeds 512 characters")
    if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 100:
        raise LiteratureEvidenceHarvesterError("rows must be an integer from 1 to 100")
    endpoint = _PROVIDER_ENDPOINTS[provider_id]
    if provider_id == "crossref":
        params = {"query.bibliographic": query_text, "rows": str(rows)}
    elif provider_id == "datacite":
        params = {"query": query_text, "page[size]": str(rows)}
    else:
        params = {
            "db": "pmc",
            "term": query_text,
            "retmax": str(rows),
            "retmode": "json",
        }
    url = endpoint + "?" + urlencode(params)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
        raise LiteratureEvidenceHarvesterError("literature request URL is not safe HTTPS")
    record = {
        "policy_version": LITERATURE_HARVESTER_POLICY_VERSION,
        "provider": provider_id,
        "method": "GET",
        "url": url,
        "metadata_discovery_only": True,
        "human_review_required_unless_policy_pinned": True,
        "scientific_status_changed": False,
        "reuse_rights_established": False,
    }
    record["request_id"] = "literature-query:" + _canonical_sha(record)[:24]
    return record


def normalize_crossref_work(item: Mapping[str, Any]) -> FederatedEvidenceCandidate:
    doi = _text(item.get("DOI"), "Crossref DOI").lower()
    raw_title = item.get("title")
    title = (
        _text(raw_title[0], "Crossref title")
        if isinstance(raw_title, list) and raw_title
        else f"Crossref work {doi}"
    )
    return FederatedEvidenceCandidate(
        provider="crossref",
        source_id=doi,
        title=title,
        evidence_class=EvidenceClass.E5_LITERATURE_CLAIM,
        trust=EvidenceTrustVector(
            source_authority="peer_reviewed",
            representation="narrative",
            sample_identity="unknown",
            acquisition_identity="unknown",
            calibration="unknown",
            independence="unresolved",
            comparability="unresolved",
            reuse="unknown",
            extraction="narrative",
        ),
        source_locator=f"doi:{doi}",
        related_identifiers=(f"doi:{doi}",),
    )


def normalize_datacite_doi(item: Mapping[str, Any]) -> FederatedEvidenceCandidate:
    doi = _text(item.get("id"), "DataCite DOI").lower()
    attributes = item.get("attributes")
    if not isinstance(attributes, Mapping):
        raise LiteratureEvidenceHarvesterError("DataCite attributes must be an object")
    titles = attributes.get("titles")
    title = f"DataCite resource {doi}"
    if isinstance(titles, list) and titles and isinstance(titles[0], Mapping):
        candidate = titles[0].get("title")
        if isinstance(candidate, str) and candidate.strip():
            title = candidate.strip()
    resource_type = str(attributes.get("types", {})).lower()
    evidence_class = (
        EvidenceClass.E2_PUBLICATION_SUPPLEMENT
        if "dataset" in resource_type
        else EvidenceClass.E5_LITERATURE_CLAIM
    )
    representation = "supplementary" if evidence_class == EvidenceClass.E2_PUBLICATION_SUPPLEMENT else "narrative"
    extraction = "underlying_data" if evidence_class == EvidenceClass.E2_PUBLICATION_SUPPLEMENT else "narrative"
    return FederatedEvidenceCandidate(
        provider="datacite",
        source_id=doi,
        title=title,
        evidence_class=evidence_class,
        trust=EvidenceTrustVector(
            source_authority="repository_curated",
            representation=representation,
            sample_identity="unknown",
            acquisition_identity="unknown",
            calibration="unknown",
            independence="unresolved",
            comparability="unresolved",
            reuse="unknown",
            extraction=extraction,
        ),
        source_locator=f"doi:{doi}",
        related_identifiers=(f"doi:{doi}",),
    )


def normalize_pmc_search_ids(ids: Sequence[str]) -> list[FederatedEvidenceCandidate]:
    result: list[FederatedEvidenceCandidate] = []
    for raw in ids:
        pmc_numeric = _text(raw, "PMC UID")
        if not pmc_numeric.isdigit():
            raise LiteratureEvidenceHarvesterError("PMC ESearch IDs must be numeric")
        pmcid = f"PMC{pmc_numeric}"
        result.append(
            FederatedEvidenceCandidate(
                provider="pmc",
                source_id=pmcid,
                title=f"PMC article {pmcid}",
                evidence_class=EvidenceClass.E5_LITERATURE_CLAIM,
                trust=EvidenceTrustVector(
                    source_authority="repository_curated",
                    representation="narrative",
                    sample_identity="unknown",
                    acquisition_identity="unknown",
                    calibration="unknown",
                    independence="unresolved",
                    comparability="unresolved",
                    reuse="unknown",
                    extraction="narrative",
                ),
                source_locator=f"pmcid:{pmcid}",
                related_identifiers=(f"pmcid:{pmcid}",),
            )
        )
    return result


def deduplicate_literature_candidates(
    candidates: Sequence[FederatedEvidenceCandidate],
) -> dict[str, Any]:
    """Group identifier-overlapping records without claiming source independence."""
    groups: list[list[str]] = []
    group_identifiers: list[set[str]] = []
    for candidate in candidates:
        identifiers = {item.lower() for item in candidate.related_identifiers}
        identifiers.add(candidate.source_id.lower())
        matching = [
            index
            for index, existing in enumerate(group_identifiers)
            if identifiers & existing
        ]
        if not matching:
            groups.append([candidate.candidate_id])
            group_identifiers.append(set(identifiers))
            continue
        first = matching[0]
        groups[first].append(candidate.candidate_id)
        group_identifiers[first].update(identifiers)
        for index in reversed(matching[1:]):
            groups[first].extend(groups.pop(index))
            group_identifiers[first].update(group_identifiers.pop(index))
    return {
        "policy_version": LITERATURE_HARVESTER_POLICY_VERSION,
        "candidate_count": len(candidates),
        "source_identity_group_count": len(groups),
        "groups": [sorted(group) for group in groups],
        "duplicate_records_are_not_independent_evidence": True,
        "scientific_status_changed": False,
    }


__all__ = [
    "LITERATURE_HARVESTER_POLICY_VERSION",
    "LiteratureEvidenceHarvesterError",
    "build_literature_discovery_request",
    "deduplicate_literature_candidates",
    "normalize_crossref_work",
    "normalize_datacite_doi",
    "normalize_pmc_search_ids",
]
