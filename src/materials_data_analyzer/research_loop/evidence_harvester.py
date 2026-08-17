"""Trusted multi-provider Evidence Harvester orchestration.

The harvester broadens evidence discovery without broadening scientific authority.  A
provider error or an empty catalog response is never interpreted as evidence that the
scientific hypothesis is false or that no evidence exists elsewhere.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .federated_provider_discovery import (
    FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION,
    discover_provider,
    federate_discovery_reports,
)
from .kernel import ResearchLoopError
from .trusted_source_discovery import (
    TRUSTED_SOURCE_DISCOVERY_SCHEMA_VERSION,
    build_evidence_search_phrase,
    discover_nist_rmm,
)

EVIDENCE_HARVESTER_SCHEMA_VERSION = "1.0"
EVIDENCE_HARVESTER_POLICY_VERSION = "1.0"
_SUPPORTED_PROVIDERS = ("nist_rmm", "datacite", "zenodo", "crossref")


class EvidenceHarvesterError(ResearchLoopError):
    """Raised when the harvesting plan itself violates its deterministic contract."""


DiscoveryCallable = Callable[[object], dict[str, Any]]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceHarvesterError(f"{field} must be non-empty text")
    if value != value.strip():
        raise EvidenceHarvesterError(f"{field} must not contain edge whitespace")
    return value


def expand_search_phrases(
    evidence_gap: object,
    *,
    query_aliases: Sequence[str] = (),
) -> list[str]:
    base = build_evidence_search_phrase(evidence_gap)
    result = [base]
    for alias in query_aliases:
        text = _text(alias, "query_alias")
        normalized = build_evidence_search_phrase(text)
        if normalized not in result:
            result.append(normalized)
    return result


def _default_discoverer(provider: str) -> DiscoveryCallable:
    if provider == "nist_rmm":
        return lambda gap: discover_nist_rmm(gap)
    if provider in {"datacite", "zenodo", "crossref"}:
        return lambda gap: discover_provider(provider, gap)
    raise EvidenceHarvesterError(f"unsupported provider: {provider}")


def _action_queue(
    *,
    nist_reports: Sequence[Mapping[str, Any]],
    federated_catalog: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for report in nist_reports:
        candidates = report.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            product_id = candidate.get("product_id")
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, str):
                continue
            action_type = (
                "nist_pdr_metadata_resolution"
                if isinstance(product_id, str) and product_id
                else "catalog_candidate_review"
            )
            key = (action_type, candidate_id)
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                {
                    "action_type": action_type,
                    "candidate_ref": candidate_id,
                    "persistent_id": product_id,
                    "provider": "nist_rmm",
                    "scientific_status_changed": False,
                }
            )
    if isinstance(federated_catalog, Mapping):
        records = federated_catalog.get("records")
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                identity = record.get("identity")
                providers = record.get("providers")
                if not isinstance(identity, str) or not isinstance(providers, list):
                    continue
                if "zenodo" in providers:
                    action_type = "zenodo_record_metadata_resolution"
                    provider = "zenodo"
                elif "datacite" in providers:
                    action_type = "persistent_identifier_resolution"
                    provider = "datacite"
                elif "crossref" in providers:
                    action_type = "literature_metadata_resolution"
                    provider = "crossref"
                else:
                    action_type = "catalog_candidate_review"
                    provider = ",".join(str(item) for item in providers)
                key = (action_type, identity)
                if key in seen:
                    continue
                seen.add(key)
                actions.append(
                    {
                        "action_type": action_type,
                        "candidate_ref": identity,
                        "persistent_id": (
                            identity.removeprefix("doi:")
                            if identity.startswith("doi:")
                            else None
                        ),
                        "provider": provider,
                        "scientific_status_changed": False,
                    }
                )
    actions.sort(
        key=lambda item: (
            str(item["action_type"]),
            str(item["provider"]),
            str(item["candidate_ref"]),
        )
    )
    return actions


def harvest_evidence(
    evidence_gap: object,
    *,
    providers: Sequence[str] = _SUPPORTED_PROVIDERS,
    query_aliases: Sequence[str] = (),
    discoverers: Mapping[str, DiscoveryCallable] | None = None,
) -> dict[str, Any]:
    provider_list: list[str] = []
    for raw in providers:
        provider = _text(raw, "provider")
        if provider not in _SUPPORTED_PROVIDERS:
            raise EvidenceHarvesterError(f"unsupported provider: {provider}")
        if provider in provider_list:
            raise EvidenceHarvesterError("providers must not contain duplicates")
        provider_list.append(provider)
    if not provider_list:
        raise EvidenceHarvesterError("providers must not be empty")
    phrases = expand_search_phrases(evidence_gap, query_aliases=query_aliases)
    reports: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    nist_reports: list[dict[str, Any]] = []
    federatable_reports: list[dict[str, Any]] = []
    for phrase in phrases:
        for provider in provider_list:
            discoverer = (
                discoverers.get(provider)
                if discoverers is not None and provider in discoverers
                else _default_discoverer(provider)
            )
            try:
                report = discoverer(phrase)
            except ResearchLoopError as exc:
                failures.append(
                    {
                        "provider": provider,
                        "search_phrase": phrase,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "scientific_negative_evidence": False,
                    }
                )
                continue
            if not isinstance(report, dict):
                raise EvidenceHarvesterError(
                    f"discoverer for {provider} must return an object"
                )
            schema = report.get("schema_version")
            if provider == "nist_rmm":
                if schema != TRUSTED_SOURCE_DISCOVERY_SCHEMA_VERSION:
                    raise EvidenceHarvesterError("NIST discovery report schema mismatch")
                nist_reports.append(report)
            else:
                if schema != FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION:
                    raise EvidenceHarvesterError(
                        f"{provider} discovery report schema mismatch"
                    )
                federatable_reports.append(report)
            reports.append(
                {
                    "provider": provider,
                    "search_phrase": phrase,
                    "response_sha256": report.get("response_sha256"),
                    "candidate_count": (
                        report.get("candidate_count")
                        if provider != "nist_rmm"
                        else report.get("returned_result_count")
                    ),
                    "report": report,
                }
            )
    federated_catalog = (
        federate_discovery_reports(federatable_reports)
        if federatable_reports
        else None
    )
    actions = _action_queue(
        nist_reports=nist_reports,
        federated_catalog=federated_catalog,
    )
    query_identity = {
        "phrases": phrases,
        "providers": provider_list,
    }
    return {
        "schema_version": EVIDENCE_HARVESTER_SCHEMA_VERSION,
        "policy_version": EVIDENCE_HARVESTER_POLICY_VERSION,
        "harvest_id": "evidence-harvest:"
        + hashlib.sha256(repr(query_identity).encode("utf-8")).hexdigest()[:24],
        "search_phrases": phrases,
        "providers": provider_list,
        "search_attempt_count": len(phrases) * len(provider_list),
        "successful_search_count": len(reports),
        "failed_search_count": len(failures),
        "reports": reports,
        "failures": failures,
        "federated_catalog": federated_catalog,
        "action_queue": actions,
        "catalog_hits_are_scientific_evidence": False,
        "provider_failure_is_scientific_negative_evidence": False,
        "empty_search_is_scientific_negative_evidence": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "EVIDENCE_HARVESTER_POLICY_VERSION",
    "EVIDENCE_HARVESTER_SCHEMA_VERSION",
    "EvidenceHarvesterError",
    "expand_search_phrases",
    "harvest_evidence",
]
