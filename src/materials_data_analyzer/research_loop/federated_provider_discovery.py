"""Trusted multi-provider catalog discovery for autonomous evidence harvesting.

Catalog metadata is useful for locating datasets and literature, but it is not itself
scientific evidence.  This module therefore records exact query/response provenance,
normalizes only provider-declared identifiers and access metadata, and keeps every hit
outside scientific intake until a source-specific adapter acquires and validates content.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode, urlparse

from .kernel import ResearchLoopError
from .public_data_acquisition import FetchResult, PublicFetcher, fetch_https_bytes
from .trusted_source_discovery import build_evidence_search_phrase

FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION = "1.0"
FEDERATED_PROVIDER_DISCOVERY_POLICY_VERSION = "1.0"
MAX_PROVIDER_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_PROVIDER_RESULTS = 25

DATACITE_HOST = "api.datacite.org"
DATACITE_ENDPOINT = f"https://{DATACITE_HOST}/dois"
CROSSREF_HOST = "api.crossref.org"
CROSSREF_ENDPOINT = f"https://{CROSSREF_HOST}/works"
ZENODO_HOST = "zenodo.org"
ZENODO_ENDPOINT = f"https://{ZENODO_HOST}/api/records"

_PROVIDER_HOSTS = {
    "datacite": DATACITE_HOST,
    "crossref": CROSSREF_HOST,
    "zenodo": ZENODO_HOST,
}


class FederatedProviderDiscoveryError(ResearchLoopError):
    """Raised when provider discovery cannot preserve its source boundary."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FederatedProviderDiscoveryError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json(raw: bytes) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FederatedProviderDiscoveryError(
            "provider response must be valid UTF-8 JSON"
        ) from exc


def _text(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise FederatedProviderDiscoveryError(f"{field} must be non-empty text")
    return value.strip()


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FederatedProviderDiscoveryError(
            "provider record must be canonical-JSON serializable"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_provider_url(url: str, *, provider: str) -> str:
    if provider not in _PROVIDER_HOSTS:
        raise FederatedProviderDiscoveryError(f"unsupported provider: {provider}")
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise FederatedProviderDiscoveryError("provider URL has invalid port") from exc
    expected_host = _PROVIDER_HOSTS[provider]
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != expected_host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise FederatedProviderDiscoveryError(
            f"provider URL must remain on exact HTTPS host {expected_host}"
        )
    path = parsed.path.rstrip("/")
    expected_prefix = {
        "datacite": "/dois",
        "crossref": "/works",
        "zenodo": "/api/records",
    }[provider]
    if not path.startswith(expected_prefix):
        raise FederatedProviderDiscoveryError(
            f"provider URL path is outside {expected_prefix}"
        )
    return url


def _doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("https://doi.org/"):
        text = text.removeprefix("https://doi.org/")
    if text.startswith("doi:"):
        text = text.removeprefix("doi:")
    if not text.startswith("10.") or "/" not in text:
        return None
    return text


def _title(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, Mapping):
                nested = item.get("title")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return "Untitled catalog record"


def _unique_text(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    for raw in values:
        if isinstance(raw, str) and raw.strip() and raw.strip() not in result:
            result.append(raw.strip())
    return result


def _discovery_record(
    *,
    provider: str,
    provider_record: Mapping[str, Any],
    persistent_id: str | None,
    title: str,
    resource_type: str | None,
    landing_url: str | None,
    related_identifiers: Sequence[str],
    rights: Sequence[str],
    content_file_count: int | None,
    content_route_hint: str,
) -> dict[str, Any]:
    record_sha = _sha(provider_record)
    stable = persistent_id or landing_url or f"record-sha256:{record_sha}"
    return {
        "candidate_id": f"{provider}:{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}",
        "provider": provider,
        "persistent_id": persistent_id,
        "title": title,
        "resource_type": resource_type,
        "landing_url": landing_url,
        "related_identifiers": sorted(set(related_identifiers)),
        "rights": sorted(set(rights)),
        "content_file_count": content_file_count,
        "content_route_hint": content_route_hint,
        "provider_record_sha256": record_sha,
        "catalog_hit_is_scientific_evidence": False,
        "requires_source_specific_content_intake": True,
        "scientific_status_changed": False,
    }


def normalize_datacite_response(
    *, response_bytes: bytes, request_url: str, search_phrase: str
) -> dict[str, Any]:
    _exact_provider_url(request_url, provider="datacite")
    root = _json(response_bytes)
    if not isinstance(root, Mapping) or not isinstance(root.get("data"), list):
        raise FederatedProviderDiscoveryError("DataCite response must contain data list")
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(root["data"]):
        if not isinstance(item, Mapping):
            raise FederatedProviderDiscoveryError(f"DataCite data[{index}] must be object")
        attributes = item.get("attributes")
        if not isinstance(attributes, Mapping):
            raise FederatedProviderDiscoveryError(
                f"DataCite data[{index}].attributes must be object"
            )
        doi = _doi(attributes.get("doi")) or _doi(item.get("id"))
        titles = attributes.get("titles")
        title = _title(titles)
        types = attributes.get("types")
        resource_type = None
        if isinstance(types, Mapping):
            for key in ("resourceTypeGeneral", "resourceType"):
                if isinstance(types.get(key), str) and types[key].strip():
                    resource_type = types[key].strip()
                    break
        related: list[str] = []
        if isinstance(attributes.get("relatedIdentifiers"), list):
            for relation in attributes["relatedIdentifiers"]:
                if isinstance(relation, Mapping):
                    identifier = relation.get("relatedIdentifier")
                    if isinstance(identifier, str) and identifier.strip():
                        related.append(identifier.strip())
        rights: list[str] = []
        if isinstance(attributes.get("rightsList"), list):
            for right in attributes["rightsList"]:
                if isinstance(right, Mapping):
                    for key in ("rightsIdentifier", "rightsUri", "rights"):
                        value = right.get(key)
                        if isinstance(value, str) and value.strip():
                            rights.append(value.strip())
        landing = attributes.get("url")
        if not isinstance(landing, str) or not landing.strip():
            landing = f"https://doi.org/{doi}" if doi else None
        candidates.append(
            _discovery_record(
                provider="datacite",
                provider_record=item,
                persistent_id=doi,
                title=title,
                resource_type=resource_type,
                landing_url=landing,
                related_identifiers=related,
                rights=rights,
                content_file_count=None,
                content_route_hint="dataset_or_repository_resolution_required",
            )
        )
    return _discovery_report(
        provider="datacite",
        request_url=request_url,
        search_phrase=search_phrase,
        response_bytes=response_bytes,
        candidates=candidates,
    )


def normalize_crossref_response(
    *, response_bytes: bytes, request_url: str, search_phrase: str
) -> dict[str, Any]:
    _exact_provider_url(request_url, provider="crossref")
    root = _json(response_bytes)
    if not isinstance(root, Mapping) or not isinstance(root.get("message"), Mapping):
        raise FederatedProviderDiscoveryError("Crossref response must contain message object")
    items = root["message"].get("items")
    if not isinstance(items, list):
        raise FederatedProviderDiscoveryError("Crossref message.items must be a list")
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise FederatedProviderDiscoveryError(
                f"Crossref message.items[{index}] must be object"
            )
        doi = _doi(item.get("DOI"))
        title = _title(item.get("title"))
        resource_type = item.get("type") if isinstance(item.get("type"), str) else None
        related: list[str] = []
        relation = item.get("relation")
        if isinstance(relation, Mapping):
            for values in relation.values():
                if isinstance(values, list):
                    for value in values:
                        if isinstance(value, Mapping):
                            identifier = value.get("id")
                            if isinstance(identifier, str) and identifier.strip():
                                related.append(identifier.strip())
        rights: list[str] = []
        if isinstance(item.get("license"), list):
            for license_item in item["license"]:
                if isinstance(license_item, Mapping):
                    url = license_item.get("URL")
                    if isinstance(url, str) and url.strip():
                        rights.append(url.strip())
        landing = item.get("URL") if isinstance(item.get("URL"), str) else None
        candidates.append(
            _discovery_record(
                provider="crossref",
                provider_record=item,
                persistent_id=doi,
                title=title,
                resource_type=resource_type,
                landing_url=landing,
                related_identifiers=related,
                rights=rights,
                content_file_count=None,
                content_route_hint="literature_metadata_only_until_fulltext_or_supplement_intake",
            )
        )
    return _discovery_report(
        provider="crossref",
        request_url=request_url,
        search_phrase=search_phrase,
        response_bytes=response_bytes,
        candidates=candidates,
    )


def _zenodo_hits(root: object) -> list[Mapping[str, Any]]:
    if isinstance(root, list):
        if not all(isinstance(item, Mapping) for item in root):
            raise FederatedProviderDiscoveryError("Zenodo legacy result list is invalid")
        return list(root)
    if not isinstance(root, Mapping):
        raise FederatedProviderDiscoveryError("Zenodo response root must be object or list")
    hits = root.get("hits")
    if isinstance(hits, Mapping) and isinstance(hits.get("hits"), list):
        values = hits["hits"]
        if not all(isinstance(item, Mapping) for item in values):
            raise FederatedProviderDiscoveryError("Zenodo hits.hits contains non-object")
        return list(values)
    raise FederatedProviderDiscoveryError("Zenodo response does not contain record hits")


def _zenodo_file_count(record: Mapping[str, Any]) -> int | None:
    files = record.get("files")
    if isinstance(files, list):
        return len(files)
    if isinstance(files, Mapping):
        entries = files.get("entries")
        if isinstance(entries, Mapping):
            return len(entries)
        if isinstance(entries, list):
            return len(entries)
        count = files.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return count
    return None


def normalize_zenodo_response(
    *, response_bytes: bytes, request_url: str, search_phrase: str
) -> dict[str, Any]:
    _exact_provider_url(request_url, provider="zenodo")
    root = _json(response_bytes)
    records = _zenodo_hits(root)
    candidates: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        metadata = record.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        doi = _doi(record.get("doi")) or _doi(metadata.get("doi"))
        pids = record.get("pids")
        if doi is None and isinstance(pids, Mapping):
            doi_obj = pids.get("doi")
            if isinstance(doi_obj, Mapping):
                doi = _doi(doi_obj.get("identifier"))
        title = _title(metadata.get("title") or record.get("title"))
        resource_type = None
        raw_type = metadata.get("resource_type") or metadata.get("upload_type")
        if isinstance(raw_type, str):
            resource_type = raw_type
        elif isinstance(raw_type, Mapping):
            for key in ("title", "id", "type"):
                if isinstance(raw_type.get(key), str) and raw_type[key].strip():
                    resource_type = raw_type[key].strip()
                    break
        related: list[str] = []
        raw_related = metadata.get("related_identifiers") or metadata.get("relatedIdentifiers")
        if isinstance(raw_related, list):
            for relation in raw_related:
                if isinstance(relation, Mapping):
                    for key in ("identifier", "relatedIdentifier"):
                        value = relation.get(key)
                        if isinstance(value, str) and value.strip():
                            related.append(value.strip())
                            break
        rights: list[str] = []
        for key in ("license", "rights"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                rights.append(value.strip())
            elif isinstance(value, Mapping):
                for nested_key in ("id", "title", "url"):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        rights.append(nested.strip())
        access = record.get("access")
        if isinstance(access, Mapping):
            status = access.get("record") or access.get("files")
            if isinstance(status, str) and status.strip():
                rights.append(f"access:{status.strip()}")
        links = record.get("links")
        landing = None
        if isinstance(links, Mapping):
            for key in ("self_html", "html", "latest_html"):
                value = links.get(key)
                if isinstance(value, str) and value.strip():
                    landing = value.strip()
                    break
        if landing is None:
            record_id = record.get("id")
            if isinstance(record_id, (str, int)) and not isinstance(record_id, bool):
                landing = f"https://zenodo.org/records/{record_id}"
        candidates.append(
            _discovery_record(
                provider="zenodo",
                provider_record=record,
                persistent_id=doi,
                title=title,
                resource_type=resource_type,
                landing_url=landing,
                related_identifiers=related,
                rights=rights,
                content_file_count=_zenodo_file_count(record),
                content_route_hint="zenodo_record_content_adapter_required",
            )
        )
    return _discovery_report(
        provider="zenodo",
        request_url=request_url,
        search_phrase=search_phrase,
        response_bytes=response_bytes,
        candidates=candidates,
    )


def _discovery_report(
    *,
    provider: str,
    request_url: str,
    search_phrase: str,
    response_bytes: bytes,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION,
        "policy_version": FEDERATED_PROVIDER_DISCOVERY_POLICY_VERSION,
        "provider": provider,
        "request_url": request_url,
        "search_phrase": search_phrase,
        "query_sha256": hashlib.sha256(search_phrase.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "candidate_count": len(candidates),
        "candidates": list(candidates),
        "catalog_hits_are_scientific_evidence": False,
        "network_failure_is_scientific_negative_evidence": False,
    }


def provider_search_url(provider: str, search_phrase: str, *, limit: int = 10) -> str:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PROVIDER_RESULTS:
        raise FederatedProviderDiscoveryError(
            f"limit must be between 1 and {MAX_PROVIDER_RESULTS}"
        )
    phrase = _text(search_phrase, "search_phrase")
    assert phrase is not None
    if provider == "datacite":
        return f"{DATACITE_ENDPOINT}?{urlencode({'query': phrase, 'page[size]': limit})}"
    if provider == "crossref":
        return f"{CROSSREF_ENDPOINT}?{urlencode({'query.bibliographic': phrase, 'rows': limit})}"
    if provider == "zenodo":
        return f"{ZENODO_ENDPOINT}?{urlencode({'q': phrase, 'size': limit})}"
    raise FederatedProviderDiscoveryError(f"unsupported provider: {provider}")


def discover_provider(
    provider: str,
    evidence_gap: object,
    *,
    fetcher: PublicFetcher = fetch_https_bytes,
    limit: int = 10,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    phrase = build_evidence_search_phrase(evidence_gap)
    request_url = provider_search_url(provider, phrase, limit=limit)
    host = _PROVIDER_HOSTS.get(provider)
    if host is None:
        raise FederatedProviderDiscoveryError(f"unsupported provider: {provider}")
    fetched = fetcher(
        request_url,
        allowed_hosts=[host],
        max_bytes=MAX_PROVIDER_RESPONSE_BYTES,
        timeout_seconds=timeout_seconds,
        headers={"Accept": "application/json"},
    )
    if not isinstance(fetched, FetchResult):
        raise FederatedProviderDiscoveryError("fetcher must return FetchResult")
    if not 200 <= fetched.status_code < 300:
        raise FederatedProviderDiscoveryError(
            f"{provider} returned status {fetched.status_code}"
        )
    _exact_provider_url(fetched.final_url, provider=provider)
    normalizer: Callable[..., dict[str, Any]] = {
        "datacite": normalize_datacite_response,
        "crossref": normalize_crossref_response,
        "zenodo": normalize_zenodo_response,
    }[provider]
    return normalizer(
        response_bytes=fetched.body,
        request_url=fetched.final_url,
        search_phrase=phrase,
    )


def federate_discovery_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deduplicate catalog identities while preserving all provider provenance."""
    by_identity: dict[str, dict[str, Any]] = {}
    for report in reports:
        if report.get("schema_version") != FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION:
            raise FederatedProviderDiscoveryError("report schema_version mismatch")
        provider = _text(report.get("provider"), "provider")
        assert provider is not None
        candidates = report.get("candidates")
        if not isinstance(candidates, list):
            raise FederatedProviderDiscoveryError("report candidates must be a list")
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise FederatedProviderDiscoveryError("candidate must be object")
            persistent = candidate.get("persistent_id")
            landing = candidate.get("landing_url")
            record_sha = _text(candidate.get("provider_record_sha256"), "provider_record_sha256")
            identity = (
                f"doi:{str(persistent).lower()}"
                if isinstance(persistent, str) and persistent
                else f"url:{landing}"
                if isinstance(landing, str) and landing
                else f"sha:{record_sha}"
            )
            entry = by_identity.setdefault(
                identity,
                {
                    "identity": identity,
                    "providers": [],
                    "candidate_refs": [],
                    "titles": [],
                    "related_identifiers": [],
                    "rights": [],
                },
            )
            if provider not in entry["providers"]:
                entry["providers"].append(provider)
            candidate_id = _text(candidate.get("candidate_id"), "candidate_id")
            assert candidate_id is not None
            entry["candidate_refs"].append(candidate_id)
            title = candidate.get("title")
            if isinstance(title, str) and title not in entry["titles"]:
                entry["titles"].append(title)
            for field in ("related_identifiers", "rights"):
                values = candidate.get(field)
                if isinstance(values, list):
                    for value in _unique_text(values):
                        if value not in entry[field]:
                            entry[field].append(value)
    records = list(by_identity.values())
    for record in records:
        for key in ("providers", "candidate_refs", "titles", "related_identifiers", "rights"):
            record[key] = sorted(record[key])
    records.sort(key=lambda item: item["identity"])
    return {
        "schema_version": FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION,
        "record_count": len(records),
        "records": records,
        "catalog_hits_are_scientific_evidence": False,
        "deduplication_does_not_establish_source_independence": True,
    }


__all__ = [
    "CROSSREF_ENDPOINT",
    "CROSSREF_HOST",
    "DATACITE_ENDPOINT",
    "DATACITE_HOST",
    "FEDERATED_PROVIDER_DISCOVERY_POLICY_VERSION",
    "FEDERATED_PROVIDER_DISCOVERY_SCHEMA_VERSION",
    "FederatedProviderDiscoveryError",
    "MAX_PROVIDER_RESULTS",
    "ZENODO_ENDPOINT",
    "ZENODO_HOST",
    "discover_provider",
    "federate_discovery_reports",
    "normalize_crossref_response",
    "normalize_datacite_response",
    "normalize_zenodo_response",
    "provider_search_url",
]
