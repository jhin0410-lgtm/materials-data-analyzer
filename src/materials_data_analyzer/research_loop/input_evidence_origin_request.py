"""Authenticate a resolvable input-evidence origin request without granting authority.

The request is a sidecar for legacy transition proposal input bindings. It binds each
`{workstream_id, role, sha256}` identity to portable paths under an explicit artifact
root, reads those exact bytes, and reuses the program-evidence/origin bridge. The
request deliberately contains no caller-controlled `origin_class` field: origin class
comes only from the exact declaration + verification byte chain.

This module prepares bytes for a later authenticated-transition snapshot step. It does
not itself publish a bundle or grant empirical scientific authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .kernel import ResearchLoopError
from .program_evidence_origin_binding import (
    ProgramEvidenceOriginBindingError,
    authenticate_program_evidence_origin_binding,
)

INPUT_EVIDENCE_ORIGIN_REQUEST_SCHEMA_VERSION = "1.0"
_INPUT_BINDING_KEYS = {"workstream_id", "role", "sha256"}
_REQUEST_ITEM_KEYS = {
    "workstream_id",
    "role",
    "sha256",
    "evidence_path",
    "origin_declaration_path",
    "origin_verification_decision_path",
}
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_WINDOWS_FORBIDDEN_CHARS = set('<>:"\\|?*')


class InputEvidenceOriginRequestError(ResearchLoopError):
    """Raised when an input-evidence origin request cannot be authenticated."""


@dataclass(frozen=True)
class InputEvidenceOriginPayload:
    """Exact immutable bytes associated with one authenticated request item."""

    workstream_id: str
    role: str
    evidence_sha256: str
    evidence_bytes: bytes
    origin_declaration_bytes: bytes
    origin_verification_decision_bytes: bytes


@dataclass(frozen=True)
class AuthenticatedInputEvidenceOriginRequest:
    """Authenticated request report plus exact bytes for later bundle snapshotting."""

    report: dict[str, Any]
    request_bytes: bytes
    payloads: tuple[InputEvidenceOriginPayload, ...]


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputEvidenceOriginRequestError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputEvidenceOriginRequestError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise InputEvidenceOriginRequestError(f"{field} root must be an object")
    return value


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputEvidenceOriginRequestError(f"{field} must be an object")
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise InputEvidenceOriginRequestError(
            f"{field} is missing required keys: {', '.join(missing)}"
        )
    if unknown:
        raise InputEvidenceOriginRequestError(
            f"{field} has unknown keys: {', '.join(unknown)}"
        )
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputEvidenceOriginRequestError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise InputEvidenceOriginRequestError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise InputEvidenceOriginRequestError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _binding(value: object, *, field: str) -> dict[str, str]:
    raw = _exact_object(
        value,
        required=set(_INPUT_BINDING_KEYS),
        allowed=set(_INPUT_BINDING_KEYS),
        field=field,
    )
    return {
        "workstream_id": _strict_text(raw["workstream_id"], f"{field}.workstream_id"),
        "role": _strict_text(raw["role"], f"{field}.role"),
        "sha256": _sha256_text(raw["sha256"], f"{field}.sha256"),
    }


def _identity(binding: Mapping[str, str]) -> tuple[str, str, str]:
    return (binding["workstream_id"], binding["role"], binding["sha256"])


def _portable_relative_parts(value: object, field: str) -> tuple[str, ...]:
    text = _strict_text(value, field)
    windows = PureWindowsPath(text)
    posix = PurePosixPath(text)
    if "\\" in text or posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise InputEvidenceOriginRequestError(
            f"{field} must be a portable relative path under artifact_root"
        )
    parts = text.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InputEvidenceOriginRequestError(
            f"{field} must not contain empty, dot, or parent components"
        )
    for part in parts:
        if any(ord(char) < 32 or char in _WINDOWS_FORBIDDEN_CHARS for char in part):
            raise InputEvidenceOriginRequestError(
                f"{field} contains a nonportable path component"
            )
        if part.endswith((" ", ".")):
            raise InputEvidenceOriginRequestError(
                f"{field} contains a nonportable trailing space or dot"
            )
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise InputEvidenceOriginRequestError(
                f"{field} contains a Windows-reserved path component"
            )
    return tuple(parts)


def _is_reparse_point(st: os.stat_result) -> bool:
    return bool(
        getattr(st, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _read_regular_under_root(
    root: Path,
    value: object,
    *,
    field: str,
) -> tuple[bytes, str]:
    parts = _portable_relative_parts(value, field)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise InputEvidenceOriginRequestError(
                f"{field} is not readable under artifact_root"
            ) from exc
        if stat.S_ISLNK(st.st_mode) or _is_reparse_point(st):
            raise InputEvidenceOriginRequestError(
                f"{field} must not traverse symlink or reparse-point components"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise InputEvidenceOriginRequestError(
                f"{field} has a non-directory parent component"
            )
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise InputEvidenceOriginRequestError(
            f"{field} escapes artifact_root"
        ) from exc
    try:
        final_stat = os.lstat(resolved)
    except OSError as exc:
        raise InputEvidenceOriginRequestError(f"{field} is not readable") from exc
    if not stat.S_ISREG(final_stat.st_mode) or _is_reparse_point(final_stat):
        raise InputEvidenceOriginRequestError(
            f"{field} must resolve to a regular non-reparse file"
        )
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise InputEvidenceOriginRequestError(f"could not read {field}") from exc
    return raw, str(PurePosixPath(*parts))


def _request_item(value: object, *, index: int) -> dict[str, Any]:
    field = f"input evidence origin request items[{index}]"
    raw = _exact_object(
        value,
        required=set(_REQUEST_ITEM_KEYS),
        allowed=set(_REQUEST_ITEM_KEYS),
        field=field,
    )
    binding = _binding(
        {
            "workstream_id": raw["workstream_id"],
            "role": raw["role"],
            "sha256": raw["sha256"],
        },
        field=f"{field}.program_evidence_binding",
    )
    return {
        "program_evidence_binding": binding,
        "evidence_path": _strict_text(raw["evidence_path"], f"{field}.evidence_path"),
        "origin_declaration_path": _strict_text(
            raw["origin_declaration_path"], f"{field}.origin_declaration_path"
        ),
        "origin_verification_decision_path": _strict_text(
            raw["origin_verification_decision_path"],
            f"{field}.origin_verification_decision_path",
        ),
    }


def authenticate_input_evidence_origin_request(
    *,
    request_bytes: bytes,
    proposal_input_evidence_bindings: Sequence[Mapping[str, Any]],
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
) -> AuthenticatedInputEvidenceOriginRequest:
    """Authenticate exact sidecar request and load exact bytes for later snapshotting."""
    if not isinstance(program_state, Mapping):
        raise InputEvidenceOriginRequestError("program_state must be an object")
    if not isinstance(request_bytes, bytes):
        raise InputEvidenceOriginRequestError("request_bytes must be bytes")
    root = Path(artifact_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise InputEvidenceOriginRequestError("artifact_root must be a directory")

    proposal_bindings: list[dict[str, str]] = []
    proposal_identities: set[tuple[str, str, str]] = set()
    for index, value in enumerate(proposal_input_evidence_bindings):
        binding = _binding(dict(value), field=f"proposal_input_evidence_bindings[{index}]")
        identity = _identity(binding)
        if identity in proposal_identities:
            raise InputEvidenceOriginRequestError(
                "proposal input evidence bindings must not contain duplicate identities"
            )
        proposal_identities.add(identity)
        proposal_bindings.append(binding)
    if not proposal_bindings:
        raise InputEvidenceOriginRequestError(
            "input evidence origin request requires at least one proposal input binding"
        )

    request_sha256 = hashlib.sha256(request_bytes).hexdigest()
    request = _json_object(request_bytes, field="input evidence origin request")
    request = _exact_object(
        request,
        required={"schema_version", "items"},
        allowed={"schema_version", "items"},
        field="input evidence origin request",
    )
    if request["schema_version"] != INPUT_EVIDENCE_ORIGIN_REQUEST_SCHEMA_VERSION:
        raise InputEvidenceOriginRequestError(
            "unsupported input evidence origin request schema_version"
        )
    raw_items = request["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise InputEvidenceOriginRequestError(
            "input evidence origin request items must be a non-empty list"
        )

    by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, value in enumerate(raw_items):
        item = _request_item(value, index=index)
        identity = _identity(item["program_evidence_binding"])
        if identity in by_identity:
            raise InputEvidenceOriginRequestError(
                "input evidence origin request contains duplicate program evidence identity"
            )
        by_identity[identity] = item
    if set(by_identity) != proposal_identities:
        raise InputEvidenceOriginRequestError(
            "input evidence origin request identities must exactly match proposal input evidence bindings"
        )

    reports: list[dict[str, Any]] = []
    payloads: list[InputEvidenceOriginPayload] = []
    for binding in proposal_bindings:
        identity = _identity(binding)
        item = by_identity[identity]
        evidence_bytes, evidence_source_path = _read_regular_under_root(
            root, item["evidence_path"], field="request evidence_path"
        )
        evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
        if evidence_sha256 != binding["sha256"]:
            raise InputEvidenceOriginRequestError(
                "request evidence bytes do not match proposal/program evidence sha256"
            )
        declaration_bytes, declaration_source_path = _read_regular_under_root(
            root,
            item["origin_declaration_path"],
            field="request origin_declaration_path",
        )
        verification_bytes, verification_source_path = _read_regular_under_root(
            root,
            item["origin_verification_decision_path"],
            field="request origin_verification_decision_path",
        )
        try:
            bridge = authenticate_program_evidence_origin_binding(
                program_state=program_state,
                program_evidence_binding=binding,
                evidence_bytes=evidence_bytes,
                origin_declaration_bytes=declaration_bytes,
                origin_verification_decision_bytes=verification_bytes,
            )
        except ProgramEvidenceOriginBindingError as exc:
            raise InputEvidenceOriginRequestError(
                "program evidence origin bridge rejected request item"
            ) from exc
        origin = bridge.get("evidence_origin_binding")
        if not isinstance(origin, Mapping):
            raise InputEvidenceOriginRequestError(
                "program evidence origin bridge returned malformed origin binding"
            )
        reports.append(
            {
                "program_evidence_binding": dict(binding),
                "origin_class": bridge["origin_class"],
                "evidence_artifact_sha256": evidence_sha256,
                "evidence_size_bytes": len(evidence_bytes),
                "origin_declaration_sha256": origin["origin_declaration_sha256"],
                "origin_declaration_size_bytes": len(declaration_bytes),
                "origin_verification_decision_sha256": origin[
                    "origin_verification_decision_sha256"
                ],
                "origin_verification_decision_size_bytes": len(verification_bytes),
                "source_paths": {
                    "evidence": evidence_source_path,
                    "origin_declaration": declaration_source_path,
                    "origin_verification_decision": verification_source_path,
                    "authoritative": False,
                },
                "program_evidence_origin_binding": dict(bridge),
                "empirical_authority_granted": False,
                "scientific_status_changed": False,
            }
        )
        payloads.append(
            InputEvidenceOriginPayload(
                workstream_id=binding["workstream_id"],
                role=binding["role"],
                evidence_sha256=evidence_sha256,
                evidence_bytes=evidence_bytes,
                origin_declaration_bytes=declaration_bytes,
                origin_verification_decision_bytes=verification_bytes,
            )
        )

    report = {
        "schema_version": INPUT_EVIDENCE_ORIGIN_REQUEST_SCHEMA_VERSION,
        "request_sha256": request_sha256,
        "items": reports,
        "all_origin_classification_records_authenticated": True,
        "request_source_paths_authoritative": False,
        "program_state_provenance_reauthenticated": False,
        "physical_origin_truth_authenticated": False,
        "verifier_identity_or_credential_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }
    return AuthenticatedInputEvidenceOriginRequest(
        report=report,
        request_bytes=request_bytes,
        payloads=tuple(payloads),
    )


__all__ = [
    "INPUT_EVIDENCE_ORIGIN_REQUEST_SCHEMA_VERSION",
    "AuthenticatedInputEvidenceOriginRequest",
    "InputEvidenceOriginPayload",
    "InputEvidenceOriginRequestError",
    "authenticate_input_evidence_origin_request",
]
