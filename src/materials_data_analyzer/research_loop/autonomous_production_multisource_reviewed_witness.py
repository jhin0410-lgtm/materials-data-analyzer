"""Independent reviewed-witness binding for retained multisource claim evidence.

The cycle-4 acquisition report is self-hashed, but self-consistency is not an
independent trust root.  This module binds its eight source identities, exact
routes/source fingerprints, and claim-match receipts to both the tracked source
registry and a separately reviewed historical witness in the trusted checkout.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate

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


def _source_projection(source: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    # Content-Type is transport metadata and may legitimately vary.  Its field must
    # nevertheless be present so omitted acquisition metadata cannot masquerade as drift.
    _require("http_content_type" in source, f"{label} HTTP content type is missing")
    content_type = source.get("http_content_type")
    _require(
        content_type is None or (isinstance(content_type, str) and bool(content_type.strip())),
        f"{label} HTTP content type is malformed",
    )
    claims = source.get("claims")
    _require(isinstance(claims, list) and claims, f"{label} claims must be non-empty")
    return {
        "request_index": source.get("request_index"),
        "source_id": source.get("source_id"),
        "requested_url": source.get("requested_url"),
        "final_url": source.get("final_url"),
        "media_type": source.get("media_type"),
        "source_sha256": source.get("source_sha256"),
        "source_size_bytes": source.get("source_size_bytes"),
        "pdf_page_count": source.get("pdf_page_count"),
        "claims": [
            _claim_projection(_mapping(claim, label=f"{label} claim"), label=f"{label} claim")
            for claim in claims
        ],
    }


def _report_projection(report: Mapping[str, Any]) -> dict[str, Any]:
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
            _source_projection(
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
                observed.get(key) == expected.get(key),
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


def verify_multisource_acquisition_against_reviewed_witness(
    report: Mapping[str, Any],
) -> None:
    """Bind every retained source/claim receipt to independent trusted checkout bytes."""

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

    witness_projection = {
        "policy_id": witness.get("policy_id"),
        "policy_sha256": witness.get("policy_sha256"),
        "registry_git_blob_sha1": witness.get("registry_git_blob_sha1"),
        "pdf_extractor": witness.get("pdf_extractor"),
        "sources": witness.get("sources"),
    }
    _require(
        _canonical_bytes(_report_projection(report))
        == _canonical_bytes(witness_projection),
        "multisource source/claim authority projection drifted from reviewed witness",
    )


__all__ = [
    "AutonomousProductionMultisourceReviewedWitnessError",
    "verify_multisource_acquisition_against_reviewed_witness",
]
