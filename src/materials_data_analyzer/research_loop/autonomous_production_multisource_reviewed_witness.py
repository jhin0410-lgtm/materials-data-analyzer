"""Independent reviewed-witness binding for retained multisource claim evidence.

Cycle-4 source evidence is self-hashed, so a verifier must not trust a source digest or claim
receipt merely because the report can be rehashed. Production therefore retains the exact bytes
from each first-pass fetch inside the acquisition report. This verifier replays those bytes through
the trusted parser and claim anchors, then applies a separately reviewed historical trust root:
mutable NIST HTML is bound by its authority-bearing claim semantics, while static NIST-hosted PDFs
remain bound by exact bytes as well as claim semantics.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from . import in625_geometry_condition_source_acquisition as _source_acquisition
from .in625_geometry_condition_multisource_policy import MAX_SOURCE_BYTES

AutonomousProductionMultisourceReviewedWitnessError = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_WITNESS_PATH = (
    "configs/research/in625_geometry_condition_multisource_reviewed_witness.v1.json"
)
_REGISTRY_PATH = (
    "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)
_EXPECTED_WITNESS_SHA256 = (
    "923eb2158a29541eacd6f1b6bbdace77ac2fa52e0365572f4953e00e12715589"
)
_EXPECTED_WITNESS_ID = "in625-geometry-condition-multisource-reviewed-witness-v1"
_SOURCE_METADATA_KEYS = (
    "source_id",
    "source_class",
    "authority",
    "title",
    "authors",
    "publication_date",
    "document_date_status",
    "doi",
)
_MAX_SOURCE_B64_CHARS = 4 * ((MAX_SOURCE_BYTES + 2) // 3)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionMultisourceReviewedWitnessError(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324 - Git object identity


def _load_trusted_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionMultisourceReviewedWitnessError(
            f"{label} must be valid trusted UTF-8 JSON"
        ) from exc
    _require(isinstance(value, dict), f"{label} root must be an object")
    return value, raw


def _claim_projection(claim: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    matches = claim.get("matches")
    _require(isinstance(matches, list), f"{label} matches must be a list")
    return {
        "claim_id": claim.get("claim_id"),
        "anchor_regex_sha256": claim.get("anchor_regex_sha256"),
        "scope": claim.get("scope"),
        "match_count": claim.get("match_count"),
        "matches": matches,
    }


def _historical_source_projection(
    source: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    claims = source.get("claims")
    _require(isinstance(claims, list) and claims, f"{label} claims must be non-empty")
    media_type = source.get("media_type")
    _require(media_type in {"html", "pdf"}, f"{label} media type is invalid")
    result: dict[str, Any] = {
        "request_index": source.get("request_index"),
        "source_id": source.get("source_id"),
        "requested_url": source.get("requested_url"),
        "final_url": source.get("final_url"),
        "media_type": media_type,
        "pdf_page_count": source.get("pdf_page_count"),
        "claims": [
            _claim_projection(
                _mapping(claim, label=f"{label} claim"),
                label=f"{label} claim",
            )
            for claim in claims
        ],
    }
    # Static publication PDFs are immutable evidence roots and remain exact-byte bound.
    # NIST CMS HTML is intentionally not raw-byte pinned: only the reviewed semantic
    # projection survives expected provider/runtime markup drift.
    if media_type == "pdf":
        result["source_sha256"] = source.get("source_sha256")
        result["source_size_bytes"] = source.get("source_size_bytes")
    return result


def _historical_report_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    extractor = _mapping(report.get("pdf_extractor"), label="multisource PDF extractor")
    version = extractor.get("version")
    _require(
        isinstance(version, str) and bool(version.strip()),
        "multisource PDF extractor version is missing",
    )
    sources = report.get("sources")
    _require(isinstance(sources, list), "multisource source records must be a list")
    return {
        "policy_id": report.get("policy_id"),
        "policy_sha256": report.get("policy_sha256"),
        "registry_git_blob_sha1": report.get("registry_git_blob_sha1"),
        "pdf_extractor": {
            "package": extractor.get("package"),
            "strict": extractor.get("strict"),
        },
        "sources": [
            _historical_source_projection(
                _mapping(source, label=f"multisource source {index}"),
                label=f"multisource source {index}",
            )
            for index, source in enumerate(sources, start=1)
        ],
    }


def _verify_registry_bindings(
    report: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> None:
    report_sources = report.get("sources")
    registry_sources = registry.get("sources")
    _require(
        isinstance(report_sources, list)
        and isinstance(registry_sources, list)
        and len(report_sources) == len(registry_sources) == 8,
        "multisource report/registry source count drifted",
    )
    for index, (raw_report, raw_registry) in enumerate(
        zip(report_sources, registry_sources, strict=True), start=1
    ):
        observed = _mapping(raw_report, label=f"multisource source {index}")
        expected = _mapping(raw_registry, label=f"trusted source registry {index}")
        for key in _SOURCE_METADATA_KEYS:
            _require(
                _canonical_bytes(observed.get(key)) == _canonical_bytes(expected.get(key)),
                f"multisource source {index} metadata drifted from trusted registry: {key}",
            )
        _require(
            observed.get("requested_url") == expected.get("url")
            and observed.get("media_type") == expected.get("media_type"),
            f"multisource source {index} route/media drifted from trusted registry",
        )
        observed_claims = observed.get("claims")
        expected_claims = expected.get("claims_under_review")
        _require(
            isinstance(observed_claims, list)
            and isinstance(expected_claims, list)
            and len(observed_claims) == len(expected_claims),
            f"multisource source {index} claim count drifted from trusted registry",
        )
        for claim_index, (raw_claim, raw_expected_claim) in enumerate(
            zip(observed_claims, expected_claims, strict=True), start=1
        ):
            claim = _mapping(
                raw_claim,
                label=f"multisource source {index} claim {claim_index}",
            )
            expected_claim = _mapping(
                raw_expected_claim,
                label=f"trusted source registry {index} claim {claim_index}",
            )
            anchor = expected_claim.get("anchor_regex")
            _require(
                isinstance(anchor, str) and bool(anchor),
                f"trusted source registry {index} claim {claim_index} anchor is missing",
            )
            _require(
                claim.get("claim_id") == expected_claim.get("claim_id")
                and claim.get("scope") == expected_claim.get("scope")
                and claim.get("anchor_regex_sha256")
                == hashlib.sha256(anchor.encode("utf-8")).hexdigest(),
                f"multisource source {index} claim {claim_index} drifted from trusted registry",
            )


def _decode_retained_source_bytes(
    source: Mapping[str, Any], *, label: str
) -> bytes:
    _require(source.get("source_bytes_persisted") is True, f"{label} retained-byte flag is false")
    encoded = source.get("source_bytes_b64")
    _require(
        isinstance(encoded, str) and 0 < len(encoded) <= _MAX_SOURCE_B64_CHARS,
        f"{label} retained source bytes are missing or exceed the bounded source budget",
    )
    try:
        body = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise AutonomousProductionMultisourceReviewedWitnessError(
            f"{label} retained source bytes are not canonical base64"
        ) from exc
    expected_size = source.get("source_size_bytes")
    _require(
        isinstance(expected_size, int)
        and not isinstance(expected_size, bool)
        and 0 < expected_size <= MAX_SOURCE_BYTES,
        f"{label} source size is not an exact bounded integer",
    )
    _require(len(body) == expected_size, f"{label} retained source byte count drifted")
    expected_sha = source.get("source_sha256")
    _require(
        isinstance(expected_sha, str)
        and expected_sha == hashlib.sha256(body).hexdigest(),
        f"{label} retained source SHA-256 drifted",
    )
    return body


def _replay_retained_source(
    observed: Mapping[str, Any],
    registered: Mapping[str, Any],
    *,
    label: str,
) -> int:
    """Recompute one source digest, parser output, and all claim receipts from retained bytes."""
    content_type = observed.get("http_content_type")
    _require(
        content_type is None
        or (isinstance(content_type, str) and bool(content_type.strip())),
        f"{label} HTTP content type is malformed",
    )
    body = _decode_retained_source_bytes(observed, label=label)
    media_type = observed.get("media_type")
    _require(
        media_type == registered.get("media_type") and media_type in {"html", "pdf"},
        f"{label} retained replay media type drifted",
    )
    if media_type == "pdf":
        source_id = observed.get("source_id")
        _require(isinstance(source_id, str) and source_id, f"{label} source id is missing")
        pages = _source_acquisition._pdf_pages(
            body,
            source_id=source_id,
            content_type=content_type,
        )
        _require(
            observed.get("pdf_page_count") == len(pages),
            f"{label} retained PDF page count drifted",
        )
    else:
        pages = _source_acquisition._html_pages(body)
        _require(
            observed.get("pdf_page_count") is None,
            f"{label} HTML source gained a PDF page count",
        )

    claim_contracts = registered.get("claims_under_review")
    observed_claims = observed.get("claims")
    _require(
        isinstance(claim_contracts, list)
        and claim_contracts
        and isinstance(observed_claims, list)
        and len(observed_claims) == len(claim_contracts),
        f"{label} retained claim contract count drifted",
    )
    replayed_claims = [
        _source_acquisition._claim_receipt(
            _mapping(claim, label=f"{label} trusted claim"),
            pages,
            is_pdf=media_type == "pdf",
        )
        for claim in claim_contracts
    ]
    _require(
        _canonical_bytes(observed_claims) == _canonical_bytes(replayed_claims),
        f"{label} claim receipts do not replay from retained source bytes",
    )
    return len(body)


def _verify_retained_source_replay(
    report: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> None:
    _require(
        report.get("source_bytes_persisted") is True,
        "multisource report did not retain exact source bytes",
    )
    _require(
        report.get("retained_source_bytes_count") == 8
        and isinstance(report.get("retained_source_bytes_count"), int)
        and not isinstance(report.get("retained_source_bytes_count"), bool),
        "multisource retained source byte count field drifted",
    )
    sources = report.get("sources")
    registry_sources = registry.get("sources")
    _require(
        isinstance(sources, list)
        and isinstance(registry_sources, list)
        and len(sources) == len(registry_sources) == 8,
        "multisource retained replay source count drifted",
    )
    total_bytes = 0
    requested_urls: set[str] = set()
    for index, (raw_source, raw_registered) in enumerate(
        zip(sources, registry_sources, strict=True), start=1
    ):
        source = _mapping(raw_source, label=f"multisource source {index}")
        registered = _mapping(
            raw_registered,
            label=f"trusted source registry {index}",
        )
        requested_url = source.get("requested_url")
        _require(
            isinstance(requested_url, str) and requested_url not in requested_urls,
            f"multisource source {index} requested URL is missing or duplicated",
        )
        requested_urls.add(requested_url)
        total_bytes += _replay_retained_source(
            source,
            registered,
            label=f"multisource source {index}",
        )
    observed_total = report.get("total_source_bytes_observed")
    _require(
        isinstance(observed_total, int)
        and not isinstance(observed_total, bool)
        and observed_total == total_bytes,
        "multisource retained total source bytes drifted",
    )


def _verify_historical_projection(
    report: Mapping[str, Any], witness: Mapping[str, Any]
) -> None:
    witness_sources = witness.get("sources")
    _require(
        isinstance(witness_sources, list),
        "multisource reviewed witness sources must be a list",
    )
    witness_projection = {
        "policy_id": witness.get("policy_id"),
        "policy_sha256": witness.get("policy_sha256"),
        "registry_git_blob_sha1": witness.get("registry_git_blob_sha1"),
        "pdf_extractor": witness.get("pdf_extractor"),
        "sources": [
            _historical_source_projection(
                _mapping(source, label=f"reviewed witness source {index}"),
                label=f"reviewed witness source {index}",
            )
            for index, source in enumerate(witness_sources, start=1)
        ],
    }
    _require(
        _canonical_bytes(_historical_report_projection(report))
        == _canonical_bytes(witness_projection),
        "multisource source/claim authority projection drifted from reviewed witness",
    )


def verify_multisource_acquisition_against_reviewed_witness(
    report: Mapping[str, Any],
) -> None:
    """Replay retained source bytes and bind their authority projection to trusted checkout bytes."""
    repository_root = _merge_gate._trusted_repository_root().resolve(strict=True)
    witness_path = (repository_root / _WITNESS_PATH).resolve(strict=True)
    registry_path = (repository_root / _REGISTRY_PATH).resolve(strict=True)
    try:
        witness_path.relative_to(repository_root)
        registry_path.relative_to(repository_root)
    except ValueError as exc:
        raise AutonomousProductionMultisourceReviewedWitnessError(
            "multisource trusted witness escaped repository root"
        ) from exc

    witness, witness_raw = _load_trusted_json(
        witness_path,
        label="multisource reviewed witness",
    )
    _require(
        hashlib.sha256(witness_raw).hexdigest() == _EXPECTED_WITNESS_SHA256,
        "multisource reviewed witness bytes drifted from pinned trust root",
    )
    _require(
        witness.get("schema_version") == "1.0"
        and witness.get("witness_id") == _EXPECTED_WITNESS_ID,
        "multisource reviewed witness identity drifted",
    )

    registry, registry_raw = _load_trusted_json(
        registry_path,
        label="multisource source registry",
    )
    registry_blob = _git_blob_sha1(registry_raw)
    _require(
        report.get("registry_git_blob_sha1") == registry_blob
        and witness.get("registry_git_blob_sha1") == registry_blob,
        "multisource source registry Git-blob binding drifted",
    )
    _verify_registry_bindings(report, registry)
    _verify_retained_source_replay(report, registry)
    _verify_historical_projection(report, witness)


__all__ = [
    "AutonomousProductionMultisourceReviewedWitnessError",
    "verify_multisource_acquisition_against_reviewed_witness",
]
