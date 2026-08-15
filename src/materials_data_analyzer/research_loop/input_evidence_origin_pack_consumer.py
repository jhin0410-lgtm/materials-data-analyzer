"""Independently re-authenticate a self-contained input-evidence origin pack.

The consumer does not trust the publisher report or manifest origin-class labels. It
re-reads the pack's exact bytes, validates bundle-relative paths/checksums, reconstructs
the request/program-evidence identities, and calls `authenticate_evidence_origin_binding`
for every evidence/declaration/verifier triple.

A successful result establishes exact origin-classification provenance only. It does not
establish empirical scientific authority or any broader scientific/autonomy claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .evidence_origin_binding import (
    EvidenceOriginBindingError,
    authenticate_evidence_origin_binding,
)
from .kernel import ResearchLoopError

INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_SCHEMA_VERSION = "1.0"
INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_POLICY_VERSION = "1.0"
_EXPECTED_PACK_SCHEMA_VERSION = "1.0"
_EXPECTED_PACK_POLICY_VERSION = "1.0"
_EXPECTED_PUBLICATION_PLATFORMS = ("windows", "linux")
_MANIFEST_NAME = "input_evidence_origin_pack_manifest.json"
_REQUEST_PATH = "request.json"
_MANIFEST_KEYS = {
    "schema_version",
    "pack_policy_version",
    "publication_platform",
    "supported_publication_platforms",
    "request_artifact",
    "items",
    "request_source_path_authoritative",
    "program_state_provenance_reauthenticated",
    "physical_origin_truth_authenticated",
    "verifier_identity_or_credential_authenticated",
    "scientific_result_validity_authenticated",
    "support_independence_established",
    "empirical_authority_granted",
    "scientific_status_changed",
    "execution_authorized",
    "positive_closeout_granted",
}
_ITEM_KEYS = {
    "program_evidence_binding",
    "origin_class",
    "evidence_artifact",
    "origin_declaration_artifact",
    "origin_verification_decision_artifact",
}
_PROGRAM_BINDING_KEYS = {"workstream_id", "role", "sha256"}
_REQUEST_KEYS = {"schema_version", "items"}
_REQUEST_ITEM_KEYS = {
    "workstream_id",
    "role",
    "sha256",
    "evidence_path",
    "origin_declaration_path",
    "origin_verification_decision_path",
}
_ARTIFACT_KEYS = {"role", "path", "sha256", "size_bytes"}
_REQUEST_ARTIFACT_KEYS = {"path", "sha256", "size_bytes"}
_ORIGIN_CLASSES = {
    "empirical_measurement",
    "external_physical_experiment",
    "computational_output",
    "analysis_output",
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


class InputEvidenceOriginPackConsumerError(ResearchLoopError):
    """Raised when exact pack provenance cannot be independently re-authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputEvidenceOriginPackConsumerError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise InputEvidenceOriginPackConsumerError(f"{field} root must be an object")
    return value


def _exact_object(
    value: object, *, expected: set[str], field: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputEvidenceOriginPackConsumerError(f"{field} must be an object")
    keys = set(value)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must use the exact key set; unknown={unknown}, missing={missing}"
        )
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputEvidenceOriginPackConsumerError(f"{field} must be non-empty text")
    if value != value.strip():
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return text


def _size(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must be a non-negative integer"
        )
    return value


def _portable_parts(value: object, field: str) -> tuple[str, ...]:
    text = _strict_text(value, field)
    windows = PureWindowsPath(text)
    posix = PurePosixPath(text)
    if "\\" in text or posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must be a portable relative pack path"
        )
    parts = text.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must not contain empty, dot, or parent components"
        )
    for part in parts:
        if any(ord(char) < 32 or char in _WINDOWS_FORBIDDEN_CHARS for char in part):
            raise InputEvidenceOriginPackConsumerError(
                f"{field} contains a nonportable path component"
            )
        if part.endswith((" ", ".")):
            raise InputEvidenceOriginPackConsumerError(
                f"{field} contains a nonportable trailing space or dot"
            )
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            raise InputEvidenceOriginPackConsumerError(
                f"{field} contains a Windows-reserved path component"
            )
    return tuple(parts)


def _is_reparse(st: os.stat_result) -> bool:
    return bool(
        getattr(st, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _pack_root(value: str | Path) -> Path:
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InputEvidenceOriginPackConsumerError("pack root is not readable") from exc
    if not root.is_dir():
        raise InputEvidenceOriginPackConsumerError("pack root must be a directory")
    return root


def _read_regular(root: Path, value: object, *, field: str) -> bytes:
    parts = _portable_parts(value, field)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise InputEvidenceOriginPackConsumerError(
                f"{field} is not readable inside the pack"
            ) from exc
        if stat.S_ISLNK(st.st_mode) or _is_reparse(st):
            raise InputEvidenceOriginPackConsumerError(
                f"{field} must not traverse symlink or reparse-point components"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise InputEvidenceOriginPackConsumerError(
                f"{field} has a non-directory parent component"
            )
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
        st = os.lstat(resolved)
    except (OSError, ValueError) as exc:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} escapes or is unreadable inside the pack"
        ) from exc
    if not stat.S_ISREG(st.st_mode) or _is_reparse(st):
        raise InputEvidenceOriginPackConsumerError(
            f"{field} must resolve to a regular non-reparse file"
        )
    try:
        return resolved.read_bytes()
    except OSError as exc:
        raise InputEvidenceOriginPackConsumerError(f"could not read {field}") from exc


def _artifact(
    root: Path,
    value: object,
    *,
    field: str,
    expected_role: str | None,
) -> tuple[dict[str, Any], bytes]:
    expected = _ARTIFACT_KEYS if expected_role is not None else _REQUEST_ARTIFACT_KEYS
    raw = _exact_object(value, expected=set(expected), field=field)
    result: dict[str, Any] = {
        "path": _strict_text(raw["path"], f"{field}.path"),
        "sha256": _sha256_text(raw["sha256"], f"{field}.sha256"),
        "size_bytes": _size(raw["size_bytes"], f"{field}.size_bytes"),
    }
    if expected_role is not None:
        role = _strict_text(raw["role"], f"{field}.role")
        if role != expected_role:
            raise InputEvidenceOriginPackConsumerError(
                f"{field}.role must be {expected_role}"
            )
        result["role"] = role
    payload = _read_regular(root, result["path"], field=f"{field}.path")
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != result["sha256"]:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} checksum does not match exact pack bytes"
        )
    if len(payload) != result["size_bytes"]:
        raise InputEvidenceOriginPackConsumerError(
            f"{field} size does not match exact pack bytes"
        )
    return result, payload


def _program_binding(value: object, *, field: str) -> dict[str, str]:
    raw = _exact_object(value, expected=set(_PROGRAM_BINDING_KEYS), field=field)
    return {
        "workstream_id": _strict_text(raw["workstream_id"], f"{field}.workstream_id"),
        "role": _strict_text(raw["role"], f"{field}.role"),
        "sha256": _sha256_text(raw["sha256"], f"{field}.sha256"),
    }


def _identity(value: Mapping[str, str]) -> tuple[str, str, str]:
    return value["workstream_id"], value["role"], value["sha256"]


def _request_identities(raw: bytes) -> list[dict[str, str]]:
    request = _exact_object(
        _json_object(raw, field="pack request snapshot"),
        expected=set(_REQUEST_KEYS),
        field="pack request snapshot",
    )
    if request["schema_version"] != "1.0":
        raise InputEvidenceOriginPackConsumerError(
            "pack request snapshot schema_version must be 1.0"
        )
    items = request["items"]
    if not isinstance(items, list) or not items:
        raise InputEvidenceOriginPackConsumerError(
            "pack request snapshot items must be a non-empty list"
        )
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, value in enumerate(items):
        item = _exact_object(
            value,
            expected=set(_REQUEST_ITEM_KEYS),
            field=f"pack request snapshot items[{index}]",
        )
        binding = _program_binding(
            {
                "workstream_id": item["workstream_id"],
                "role": item["role"],
                "sha256": item["sha256"],
            },
            field=f"pack request snapshot items[{index}] identity",
        )
        identity = _identity(binding)
        if identity in seen:
            raise InputEvidenceOriginPackConsumerError(
                "pack request snapshot contains duplicate evidence identity"
            )
        seen.add(identity)
        # Source paths are deliberately not resolved here. They refer to the publisher's
        # artifact root and are non-authoritative after the pack becomes self-contained.
        for path_field in (
            "evidence_path",
            "origin_declaration_path",
            "origin_verification_decision_path",
        ):
            _portable_parts(
                item[path_field],
                f"pack request snapshot items[{index}].{path_field}",
            )
        result.append(binding)
    return result


def authenticate_input_evidence_origin_pack(pack_root: str | Path) -> dict[str, Any]:
    """Re-authenticate exact self-contained pack bytes without granting empirical authority."""
    root = _pack_root(pack_root)
    manifest_bytes = _read_regular(root, _MANIFEST_NAME, field="pack manifest")
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = _exact_object(
        _json_object(manifest_bytes, field="pack manifest"),
        expected=set(_MANIFEST_KEYS),
        field="pack manifest",
    )
    if manifest["schema_version"] != _EXPECTED_PACK_SCHEMA_VERSION:
        raise InputEvidenceOriginPackConsumerError("unsupported pack schema_version")
    if manifest["pack_policy_version"] != _EXPECTED_PACK_POLICY_VERSION:
        raise InputEvidenceOriginPackConsumerError("unsupported pack policy version")
    publication_platform = manifest["publication_platform"]
    if publication_platform not in _EXPECTED_PUBLICATION_PLATFORMS:
        raise InputEvidenceOriginPackConsumerError(
            "pack publication_platform is outside the supported producer contract"
        )
    if manifest["supported_publication_platforms"] != list(
        _EXPECTED_PUBLICATION_PLATFORMS
    ):
        raise InputEvidenceOriginPackConsumerError(
            "pack supported_publication_platforms diverge from the expected producer contract"
        )
    if manifest["request_source_path_authoritative"] is not False:
        raise InputEvidenceOriginPackConsumerError(
            "pack must keep request source paths non-authoritative"
        )
    for field in (
        "program_state_provenance_reauthenticated",
        "physical_origin_truth_authenticated",
        "verifier_identity_or_credential_authenticated",
        "scientific_result_validity_authenticated",
        "support_independence_established",
        "empirical_authority_granted",
        "scientific_status_changed",
        "execution_authorized",
        "positive_closeout_granted",
    ):
        if manifest[field] is not False:
            raise InputEvidenceOriginPackConsumerError(
                f"pack manifest must preserve non-authority boundary: {field}=false"
            )

    request_binding, request_bytes = _artifact(
        root,
        manifest["request_artifact"],
        field="pack request_artifact",
        expected_role=None,
    )
    if request_binding["path"] != _REQUEST_PATH:
        raise InputEvidenceOriginPackConsumerError(
            "pack request_artifact must bind the fixed request.json snapshot"
        )
    request_bindings = _request_identities(request_bytes)
    request_identity_set = {_identity(item) for item in request_bindings}

    raw_items = manifest["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise InputEvidenceOriginPackConsumerError(
            "pack manifest items must be a non-empty list"
        )
    results: list[dict[str, Any]] = []
    manifest_identity_set: set[tuple[str, str, str]] = set()
    used_paths: set[str] = {_MANIFEST_NAME, _REQUEST_PATH}
    for index, value in enumerate(raw_items):
        item = _exact_object(
            value,
            expected=set(_ITEM_KEYS),
            field=f"pack manifest items[{index}]",
        )
        binding = _program_binding(
            item["program_evidence_binding"],
            field=f"pack manifest items[{index}].program_evidence_binding",
        )
        identity = _identity(binding)
        if identity in manifest_identity_set:
            raise InputEvidenceOriginPackConsumerError(
                "pack manifest contains duplicate program evidence identity"
            )
        manifest_identity_set.add(identity)

        evidence_binding, evidence_bytes = _artifact(
            root,
            item["evidence_artifact"],
            field=f"pack manifest items[{index}].evidence_artifact",
            expected_role="evidence",
        )
        declaration_binding, declaration_bytes = _artifact(
            root,
            item["origin_declaration_artifact"],
            field=f"pack manifest items[{index}].origin_declaration_artifact",
            expected_role="origin_declaration",
        )
        verification_binding, verification_bytes = _artifact(
            root,
            item["origin_verification_decision_artifact"],
            field=f"pack manifest items[{index}].origin_verification_decision_artifact",
            expected_role="origin_verification_decision",
        )
        expected_root = f"items/{index:04d}"
        expected_paths = {
            "evidence": f"{expected_root}/evidence.bin",
            "origin_declaration": f"{expected_root}/origin_declaration.json",
            "origin_verification_decision": (
                f"{expected_root}/origin_verification_decision.json"
            ),
        }
        actual_paths = {
            "evidence": evidence_binding["path"],
            "origin_declaration": declaration_binding["path"],
            "origin_verification_decision": verification_binding["path"],
        }
        if actual_paths != expected_paths:
            raise InputEvidenceOriginPackConsumerError(
                "pack item snapshot paths do not match the deterministic producer shape"
            )
        for artifact in (
            evidence_binding,
            declaration_binding,
            verification_binding,
        ):
            path = str(artifact["path"])
            if path in used_paths:
                raise InputEvidenceOriginPackConsumerError(
                    "pack manifest reuses one snapshot path for multiple authority roles"
                )
            used_paths.add(path)

        if evidence_binding["sha256"] != binding["sha256"]:
            raise InputEvidenceOriginPackConsumerError(
                "pack evidence snapshot SHA does not match program evidence identity"
            )
        try:
            recomputed = authenticate_evidence_origin_binding(
                evidence_bytes=evidence_bytes,
                origin_declaration_bytes=declaration_bytes,
                origin_verification_decision_bytes=verification_bytes,
            )
        except EvidenceOriginBindingError as exc:
            raise InputEvidenceOriginPackConsumerError(
                "pack origin-classification bytes failed independent reauthentication"
            ) from exc

        manifest_origin_class = _strict_text(
            item["origin_class"],
            f"pack manifest items[{index}].origin_class",
        )
        if manifest_origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackConsumerError(
                "pack manifest contains unsupported origin_class"
            )
        if recomputed["origin_class"] != manifest_origin_class:
            raise InputEvidenceOriginPackConsumerError(
                "pack manifest origin_class does not match independently reauthenticated bytes"
            )
        if recomputed["evidence_artifact_sha256"] != binding["sha256"]:
            raise InputEvidenceOriginPackConsumerError(
                "independent origin binding evidence SHA diverges from program identity"
            )
        if recomputed["origin_declaration_sha256"] != declaration_binding["sha256"]:
            raise InputEvidenceOriginPackConsumerError(
                "independent origin declaration SHA diverges from pack binding"
            )
        if (
            recomputed["origin_verification_decision_sha256"]
            != verification_binding["sha256"]
        ):
            raise InputEvidenceOriginPackConsumerError(
                "independent origin verifier SHA diverges from pack binding"
            )
        results.append(
            {
                "program_evidence_binding": dict(binding),
                "origin_class": recomputed["origin_class"],
                "evidence_id": recomputed["evidence_id"],
                "origin_verification_decision_id": recomputed[
                    "verification_decision_id"
                ],
                "origin_classification_domain_verified": True,
                "exact_evidence_origin_provenance_authenticated": True,
            }
        )

    if manifest_identity_set != request_identity_set:
        raise InputEvidenceOriginPackConsumerError(
            "pack request snapshot identities do not exactly match manifest item identities"
        )

    return {
        "schema_version": INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_SCHEMA_VERSION,
        "consumer_policy_version": INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_POLICY_VERSION,
        "pack_schema_version": _EXPECTED_PACK_SCHEMA_VERSION,
        "pack_policy_version": _EXPECTED_PACK_POLICY_VERSION,
        "pack_manifest_sha256": manifest_sha,
        "request_sha256": request_binding["sha256"],
        "items": results,
        "all_items_exact_evidence_origin_provenance_authenticated": True,
        "request_identity_set_authenticated": True,
        "manifest_origin_class_used_as_authority_without_reauthentication": False,
        "program_state_provenance_reauthenticated": False,
        "physical_origin_truth_authenticated": False,
        "verifier_identity_or_credential_authenticated": False,
        "scientific_result_validity_authenticated": False,
        "support_independence_established": False,
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
        "pack_immutability_after_return_authenticated": False,
        "hostile_concurrent_writer_resistance_authenticated": False,
    }


__all__ = [
    "INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_POLICY_VERSION",
    "INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_SCHEMA_VERSION",
    "InputEvidenceOriginPackConsumerError",
    "authenticate_input_evidence_origin_pack",
]
