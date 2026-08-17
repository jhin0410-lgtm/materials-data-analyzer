"""Policy-bounded discovery of external research evidence from trusted repositories.

Discovery is deliberately weaker than scientific intake: a catalog hit may justify fetching
repository metadata, but it never upgrades a scientific claim. Only exact allow-listed HTTPS
providers may run without per-query human approval. Unknown providers remain outside this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode, urlparse

from .kernel import ResearchLoopError
from .public_data_acquisition import FetchResult, PublicFetcher, fetch_https_bytes

TRUSTED_SOURCE_DISCOVERY_SCHEMA_VERSION = "1.0"
TRUSTED_SOURCE_DISCOVERY_POLICY_VERSION = "1.0"
NIST_RMM_HOST = "data.nist.gov"
NIST_RMM_SEARCH_ENDPOINT = f"https://{NIST_RMM_HOST}/rmm/records"
NIST_RMM_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_SEARCH_PHRASE_CHARS = 512

AUTO = "AUTO"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_PDR_PRODUCT_RE = re.compile(r"(?<![A-Za-z0-9])mds[0-9A-Za-z._:-]+", re.IGNORECASE)


class TrustedSourceDiscoveryError(ResearchLoopError):
    """Raised when trusted-source discovery cannot preserve its trust boundary."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrustedSourceDiscoveryError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustedSourceDiscoveryError(f"{field} must be non-empty text")
    if value != value.strip():
        raise TrustedSourceDiscoveryError(f"{field} must not contain edge whitespace")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrustedSourceDiscoveryError("value must be canonical-JSON serializable") from exc


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustedSourceDiscoveryError("discovery response must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise TrustedSourceDiscoveryError("discovery response root must be an object")
    return value


def _validate_exact_nist_rmm_url(value: object, *, field: str) -> str:
    text = _strict_text(value, field)
    parsed = urlparse(text)
    try:
        port = parsed.port
    except ValueError as exc:
        raise TrustedSourceDiscoveryError(f"{field} contains an invalid port") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != NIST_RMM_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
        or not parsed.path.startswith("/rmm/records")
    ):
        raise TrustedSourceDiscoveryError(f"{field} is outside exact NIST RMM HTTPS")
    return text


def _flatten_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for nested in value.values():
            result.extend(_flatten_text(nested))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for nested in value:
            result.extend(_flatten_text(nested))
        return result
    return []


def _tokens(value: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(value)]


def build_evidence_search_phrase(evidence_gap: object) -> str:
    """Create a deterministic, bounded search phrase from an evidence-gap object or text."""
    if isinstance(evidence_gap, str):
        raw_parts = [evidence_gap]
    elif isinstance(evidence_gap, Mapping):
        preferred = (
            "material",
            "process",
            "measurement",
            "response",
            "condition",
            "research_question",
            "evidence_requirement",
            "objective",
        )
        raw_parts = []
        for key in preferred:
            if key in evidence_gap:
                raw_parts.extend(_flatten_text(evidence_gap[key]))
        if not raw_parts:
            raw_parts = _flatten_text(evidence_gap)
    else:
        raise TrustedSourceDiscoveryError("evidence_gap must be text or an object")

    ordered: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        for token in _tokens(part):
            if token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    if not ordered:
        raise TrustedSourceDiscoveryError("evidence_gap does not contain searchable tokens")
    phrase = " ".join(ordered)
    if len(phrase) > MAX_SEARCH_PHRASE_CHARS:
        phrase = phrase[:MAX_SEARCH_PHRASE_CHARS].rstrip()
    return phrase


def nist_rmm_search_endpoint(search_phrase: str) -> str:
    phrase = _strict_text(search_phrase, "search_phrase")
    if len(phrase) > MAX_SEARCH_PHRASE_CHARS:
        raise TrustedSourceDiscoveryError(
            f"search_phrase exceeds {MAX_SEARCH_PHRASE_CHARS} characters"
        )
    return f"{NIST_RMM_SEARCH_ENDPOINT}?{urlencode({'searchphrase': phrase})}"


def _public_status(record: Mapping[str, Any]) -> tuple[bool, str]:
    access = record.get("accessLevel")
    if access is not None:
        if access == "public":
            return True, "accessLevel=public"
        return False, f"accessLevel={access!r}"
    types = record.get("@type")
    if isinstance(types, list) and "nrdp:PublicDataResource" in types:
        return True, "@type=nrdp:PublicDataResource"
    return False, "public status not explicit in discovery record"


def _record_product_id(record: Mapping[str, Any]) -> str | None:
    direct = record.get("ediid")
    if isinstance(direct, str) and _PDR_PRODUCT_RE.fullmatch(direct):
        return direct
    for key in ("@id", "identifier"):
        for text in _flatten_text(record.get(key)):
            match = _PDR_PRODUCT_RE.search(text)
            if match:
                return match.group(0)
    return None


def _record_title(record: Mapping[str, Any]) -> str:
    title = record.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    if isinstance(title, list):
        for item in title:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return "Untitled NIST PDR record"


def _relevance_score(search_phrase: str, record: Mapping[str, Any], *, product_id: str | None) -> float:
    query_tokens = set(_tokens(search_phrase))
    haystack = " ".join(_flatten_text(record)).lower()
    if not query_tokens:
        return 0.0
    matched = sum(1 for token in query_tokens if token in haystack)
    coverage = matched / len(query_tokens)
    exact_bonus = 0.15 if search_phrase.lower() in haystack else 0.0
    id_bonus = 0.05 if product_id else 0.0
    return round(min(1.0, coverage * 0.8 + exact_bonus + id_bonus), 6)


def normalize_nist_rmm_search_response(
    *,
    response_bytes: bytes,
    search_phrase: str,
    request_url: str,
) -> dict[str, Any]:
    """Normalize one exact NIST RMM response without making scientific claims."""
    if not isinstance(response_bytes, bytes):
        raise TrustedSourceDiscoveryError("response_bytes must be exact bytes")
    endpoint = _validate_exact_nist_rmm_url(request_url, field="request_url")
    root = _json_object(response_bytes)
    result_data = root.get("ResultData")
    if not isinstance(result_data, list):
        raise TrustedSourceDiscoveryError("NIST RMM ResultData must be a list")
    result_count = root.get("ResultCount")
    if isinstance(result_count, bool) or not isinstance(result_count, int) or result_count < 0:
        raise TrustedSourceDiscoveryError("NIST RMM ResultCount must be a non-negative integer")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(result_data):
        if not isinstance(raw, Mapping):
            raise TrustedSourceDiscoveryError(f"ResultData[{index}] must be an object")
        product_id = _record_product_id(raw)
        is_public, public_basis = _public_status(raw)
        title = _record_title(raw)
        record_sha = hashlib.sha256(_canonical_json_bytes(raw)).hexdigest()
        decision = AUTO if is_public else REVIEW_REQUIRED
        reasons = [] if is_public else ["public_access_not_explicit_in_search_record"]
        normalized.append(
            {
                "candidate_id": f"nist-rmm:{product_id or record_sha[:16]}",
                "provider": "nist_rmm",
                "provider_host": NIST_RMM_HOST,
                "title": title,
                "product_id": product_id,
                "discovery_decision": decision,
                "discovery_reason_codes": reasons,
                "public_status_basis": public_basis,
                "acquisition_metadata_resolvable": product_id is not None,
                "relevance_score": _relevance_score(
                    search_phrase, raw, product_id=product_id
                ),
                "record_sha256": record_sha,
                "requires_scientific_intake": True,
                "scientific_status_changed": False,
                "limitations": [
                    "Catalog relevance does not establish experimental comparability.",
                    "Discovery metadata does not establish machine, calibration, material-state, or replicate identity.",
                ],
            }
        )
    normalized.sort(
        key=lambda item: (
            -float(item["relevance_score"]),
            str(item["product_id"] or ""),
            str(item["candidate_id"]),
        )
    )
    return {
        "schema_version": TRUSTED_SOURCE_DISCOVERY_SCHEMA_VERSION,
        "policy_version": TRUSTED_SOURCE_DISCOVERY_POLICY_VERSION,
        "provider": "nist_rmm",
        "request_url": endpoint,
        "search_phrase": search_phrase,
        "query_sha256": hashlib.sha256(search_phrase.encode("utf-8")).hexdigest(),
        "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "reported_result_count": result_count,
        "returned_result_count": len(normalized),
        "candidates": normalized,
        "network_failure_is_scientific_negative_evidence": False,
    }


def discover_nist_rmm(
    evidence_gap: object,
    *,
    fetcher: PublicFetcher = fetch_https_bytes,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Search NIST RMM under a fixed provider allow-list; no human approval is needed."""
    phrase = build_evidence_search_phrase(evidence_gap)
    endpoint = nist_rmm_search_endpoint(phrase)
    fetched = fetcher(
        endpoint,
        allowed_hosts=[NIST_RMM_HOST],
        max_bytes=NIST_RMM_MAX_RESPONSE_BYTES,
        timeout_seconds=timeout_seconds,
        headers={"Accept": "application/json"},
    )
    if not isinstance(fetched, FetchResult):
        raise TrustedSourceDiscoveryError("fetcher must return FetchResult")
    if not 200 <= fetched.status_code < 300:
        raise TrustedSourceDiscoveryError(
            f"NIST RMM search returned status {fetched.status_code}"
        )
    _validate_exact_nist_rmm_url(fetched.final_url, field="NIST RMM final URL")
    return normalize_nist_rmm_search_response(
        response_bytes=fetched.body,
        search_phrase=phrase,
        request_url=fetched.final_url,
    )


def trusted_provider_authorization(provider: str) -> dict[str, Any]:
    """Return the narrow policy decision used by the autonomous executor."""
    if provider == "nist_rmm":
        return {
            "provider": provider,
            "decision": AUTO,
            "human_approval_required": False,
            "reason_codes": ["exact_https_provider_allowlist", "public_catalog_search_only"],
        }
    return {
        "provider": provider,
        "decision": REVIEW_REQUIRED,
        "human_approval_required": True,
        "reason_codes": ["provider_not_in_trusted_discovery_allowlist"],
    }


__all__ = [
    "AUTO",
    "BLOCKED",
    "MAX_SEARCH_PHRASE_CHARS",
    "NIST_RMM_HOST",
    "NIST_RMM_MAX_RESPONSE_BYTES",
    "NIST_RMM_SEARCH_ENDPOINT",
    "REVIEW_REQUIRED",
    "TRUSTED_SOURCE_DISCOVERY_POLICY_VERSION",
    "TRUSTED_SOURCE_DISCOVERY_SCHEMA_VERSION",
    "TrustedSourceDiscoveryError",
    "build_evidence_search_phrase",
    "discover_nist_rmm",
    "nist_rmm_search_endpoint",
    "normalize_nist_rmm_search_response",
    "trusted_provider_authorization",
]
