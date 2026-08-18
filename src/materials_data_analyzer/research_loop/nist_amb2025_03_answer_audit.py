"""Second-pass provenance audit for NIST AMB2025-03 fatigue answer data.

The public NERDm record exposes a post-challenge workbook containing both treatment
conditions, but that DataFile currently lacks a source-published checksum.  This audit
records the existence of the adjacent answer artifact without weakening the generic
checksum-bound automatic acquisition policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from .nist_amb2025_03_metadata_contract import (
    NistAmb202503MetadataContractError,
    validate_amb2025_03_metadata,
)

ANSWER_FILEPATH = "answers_data/fatigue_both_conditions.xlsx"
NIST_HOST = "data.nist.gov"


class NistAmb202503AnswerAuditError(ValueError):
    """Raised when exact NERDm metadata cannot support the answer-data audit."""


def _json_object(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise NistAmb202503AnswerAuditError("NERDm metadata must be exact bytes")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise NistAmb202503AnswerAuditError(
                    f"NERDm metadata repeats JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistAmb202503AnswerAuditError(
            "NERDm metadata must be UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistAmb202503AnswerAuditError("NERDm root must be an object")
    return value


def _exact_nist_download_url(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise NistAmb202503AnswerAuditError(
            "answer DataFile downloadURL must be exact non-empty text"
        )
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise NistAmb202503AnswerAuditError(
            "answer DataFile downloadURL contains invalid port"
        ) from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != NIST_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise NistAmb202503AnswerAuditError(
            "answer DataFile downloadURL is outside exact NIST HTTPS"
        )
    return value


def _source_checksum(component: Mapping[str, Any]) -> dict[str, str] | None:
    raw = component.get("checksum")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise NistAmb202503AnswerAuditError(
            "answer DataFile checksum metadata is malformed"
        )
    digest = raw.get("hash")
    algorithm = raw.get("algorithm")
    if isinstance(algorithm, Mapping):
        tag = algorithm.get("tag")
    else:
        tag = algorithm
    if not isinstance(tag, str) or not isinstance(digest, str):
        raise NistAmb202503AnswerAuditError(
            "answer DataFile checksum lacks algorithm/hash"
        )
    return {"algorithm": tag.lower(), "digest": digest.lower()}


def audit_amb2025_03_answer_metadata(metadata_bytes: bytes) -> dict[str, Any]:
    """Audit whether the public both-condition fatigue answer can be auto-acquired."""

    try:
        scope = validate_amb2025_03_metadata(metadata_bytes)
    except NistAmb202503MetadataContractError as exc:
        raise NistAmb202503AnswerAuditError(str(exc)) from exc
    metadata = _json_object(metadata_bytes)
    components = metadata.get("components")
    if not isinstance(components, list):
        raise NistAmb202503AnswerAuditError("NERDm components must be a list")
    matches = [
        item
        for item in components
        if isinstance(item, Mapping) and item.get("filepath") == ANSWER_FILEPATH
    ]
    if len(matches) != 1:
        raise NistAmb202503AnswerAuditError(
            f"expected exactly one {ANSWER_FILEPATH!r} DataFile, got {len(matches)}"
        )
    component = matches[0]
    types = component.get("@type")
    if not isinstance(types, list) or "nrdp:DataFile" not in types:
        raise NistAmb202503AnswerAuditError(
            "both-condition fatigue answer is not an explicit NERDm DataFile"
        )
    size = component.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise NistAmb202503AnswerAuditError(
            "both-condition fatigue answer lacks a positive exact byte size"
        )
    download_url = _exact_nist_download_url(component.get("downloadURL"))
    checksum = _source_checksum(component)
    checksum_bound = (
        checksum is not None
        and checksum["algorithm"].replace("-", "") == "sha256"
        and len(checksum["digest"]) == 64
    )

    report = {
        "schema_version": "1.0",
        "source": {
            "product_id": scope["product_id"],
            "source_version": scope["source_version"],
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        },
        "answer_artifact": {
            "filepath": ANSWER_FILEPATH,
            "size_bytes": size,
            "download_url": download_url,
            "source_checksum": checksum,
            "source_sha256_bound": checksum_bound,
            "public_datafile_discovered": True,
        },
        "first_pass_weakness_addressed": (
            "A both-condition fatigue answer DataFile exists in the same authoritative NIST record, "
            "so the earlier calibration-only absence of 800VAC outcomes is not a permanent data absence."
        ),
        "automatic_acquisition_eligible": checksum_bound,
        "automatic_acquisition_decision": (
            "AUTO" if checksum_bound else "REVIEW_REQUIRED_SOURCE_INTEGRITY"
        ),
        "new_blocker": (
            None
            if checksum_bound
            else "authoritative_answer_datafile_missing_source_sha256_checksum"
        ),
        "bounded_stop": not checksum_bound,
        "bounded_stop_reason": (
            None
            if checksum_bound
            else "Do not weaken the checksum-bound NIST acquisition contract merely to consume post-challenge answer data."
        ),
        "recommended_followup": (
            "Acquire and intake the both-condition workbook through the existing NIST PDR path if a source-published SHA-256 becomes available or an explicitly reviewed lower-integrity acquisition route is approved."
        ),
        "model_training_authorized": False,
        "treatment_effect_claim_authorized": False,
        "scientific_support_established": False,
        "scientific_status_changed": False,
    }
    return report


__all__ = [
    "ANSWER_FILEPATH",
    "NistAmb202503AnswerAuditError",
    "audit_amb2025_03_answer_metadata",
]
