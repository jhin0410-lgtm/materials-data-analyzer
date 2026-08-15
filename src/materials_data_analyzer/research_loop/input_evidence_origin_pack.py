"""Publish a self-contained input-evidence origin provenance pack.

The publisher re-runs the exact input-evidence origin request authenticator, captures the
request/evidence/declaration/verifier bytes into a private staging tree, validates the
written bytes, and atomically publishes the directory without replacement on Windows or
Linux. The pack is provenance-only: it does not grant empirical/scientific authority.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .input_evidence_origin_request import (
    InputEvidenceOriginRequestError,
    authenticate_input_evidence_origin_request,
)
from .kernel import ResearchLoopError

INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION = "1.0"
INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION = "1.0"
INPUT_EVIDENCE_ORIGIN_PACK_SUPPORTED_PLATFORMS = ("windows", "linux")
_ORIGIN_CLASSES = {
    "empirical_measurement",
    "external_physical_experiment",
    "computational_output",
    "analysis_output",
}
_PACK_MANIFEST = "input_evidence_origin_pack_manifest.json"
_REQUEST_SNAPSHOT = "request.json"


class InputEvidenceOriginPackError(ResearchLoopError):
    """Raised when a self-contained evidence-origin pack cannot be published."""


def _platform_name() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise InputEvidenceOriginPackError(
        "input-evidence origin pack publication is supported only on Windows and Linux"
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_reparse_point(st: os.stat_result) -> bool:
    return bool(
        getattr(st, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _read_source_regular_file(value: str | Path, *, field: str) -> tuple[Path, bytes]:
    path = Path(value).expanduser()
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise InputEvidenceOriginPackError(f"{field} is not readable") from exc
    if stat.S_ISLNK(st.st_mode) or _is_reparse_point(st) or not stat.S_ISREG(st.st_mode):
        raise InputEvidenceOriginPackError(
            f"{field} must be a regular non-link, non-reparse file"
        )
    try:
        resolved = path.resolve(strict=True)
        raw = resolved.read_bytes()
    except OSError as exc:
        raise InputEvidenceOriginPackError(f"could not read {field}") from exc
    return resolved, raw


def _binding(*, path: str, raw: bytes, role: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }
    if role is not None:
        result["role"] = role
    return result


def _item_paths(index: int) -> dict[str, str]:
    root = f"items/{index:04d}"
    return {
        "evidence": f"{root}/evidence.bin",
        "origin_declaration": f"{root}/origin_declaration.json",
        "origin_verification_decision": f"{root}/origin_verification_decision.json",
    }


def _write_payload(root: Path, relative: str, raw: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise InputEvidenceOriginPackError(
            f"staged pack path already exists: {relative}"
        ) from exc


def _read_staged(root: Path, relative: str) -> bytes:
    path = root / relative
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise InputEvidenceOriginPackError(
            f"staged pack path is not readable: {relative}"
        ) from exc
    if stat.S_ISLNK(st.st_mode) or _is_reparse_point(st) or not stat.S_ISREG(st.st_mode):
        raise InputEvidenceOriginPackError(
            f"staged pack path must remain a regular non-link file: {relative}"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InputEvidenceOriginPackError(
            f"could not read staged pack path: {relative}"
        ) from exc


def _validate_written_payloads(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, expected in payloads.items():
        if _read_staged(root, relative) != expected:
            raise InputEvidenceOriginPackError(
                f"staged evidence-origin pack bytes changed: {relative}"
            )


def _atomic_publish_no_replace(source: Path, destination: Path) -> None:
    if os.name == "nt":
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise InputEvidenceOriginPackError(
                f"output_dir appeared during publication: {destination}"
            ) from exc
        except OSError as exc:
            if destination.exists():
                raise InputEvidenceOriginPackError(
                    f"output_dir appeared during publication: {destination}"
                ) from exc
            raise
        return

    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise InputEvidenceOriginPackError(
                "atomic no-replace pack publication requires renameat2 on Linux"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        rc = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        if rc != 0:
            error = ctypes.get_errno()
            if error in {errno.EEXIST, errno.ENOTEMPTY}:
                raise InputEvidenceOriginPackError(
                    f"output_dir appeared during publication: {destination}"
                )
            raise InputEvidenceOriginPackError(
                f"atomic no-replace pack publication failed with errno {error}"
            )
        return

    raise InputEvidenceOriginPackError("unsupported pack publication platform")


def publish_input_evidence_origin_pack(
    *,
    request_path: str | Path,
    proposal_input_evidence_bindings: Sequence[Mapping[str, Any]],
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Publish exact authenticated input-evidence origin bytes as a standalone pack."""
    publication_platform = _platform_name()
    request_source, request_bytes = _read_source_regular_file(
        request_path, field="input evidence origin request"
    )
    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    if not artifacts.is_dir():
        raise InputEvidenceOriginPackError("artifact_root must be a directory")
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise InputEvidenceOriginPackError(f"output_dir must not already exist: {output}")

    try:
        authenticated = authenticate_input_evidence_origin_request(
            request_bytes=request_bytes,
            proposal_input_evidence_bindings=proposal_input_evidence_bindings,
            program_state=program_state,
            artifact_root=artifacts,
        )
    except InputEvidenceOriginRequestError as exc:
        raise InputEvidenceOriginPackError(
            "input evidence origin request authentication failed"
        ) from exc

    report_items = authenticated.report.get("items")
    if not isinstance(report_items, list) or len(report_items) != len(authenticated.payloads):
        raise InputEvidenceOriginPackError("authenticated request returned inconsistent item payloads")

    payloads: dict[str, bytes] = {_REQUEST_SNAPSHOT: authenticated.request_bytes}
    manifest_items: list[dict[str, Any]] = []
    for index, (payload, report_item) in enumerate(
        zip(authenticated.payloads, report_items, strict=True)
    ):
        if not isinstance(report_item, Mapping):
            raise InputEvidenceOriginPackError("authenticated request item report is malformed")
        paths = _item_paths(index)
        payloads[paths["evidence"]] = payload.evidence_bytes
        payloads[paths["origin_declaration"]] = payload.origin_declaration_bytes
        payloads[paths["origin_verification_decision"]] = (
            payload.origin_verification_decision_bytes
        )
        program_binding = report_item.get("program_evidence_binding")
        if not isinstance(program_binding, Mapping):
            raise InputEvidenceOriginPackError(
                "authenticated request item lacks program evidence identity"
            )
        report_identity = (
            program_binding.get("workstream_id"),
            program_binding.get("role"),
            program_binding.get("sha256"),
        )
        payload_identity = (
            payload.workstream_id,
            payload.role,
            payload.evidence_sha256,
        )
        if report_identity != payload_identity:
            raise InputEvidenceOriginPackError(
                "authenticated request report/payload identity diverged"
            )
        if _sha256(payload.evidence_bytes) != payload.evidence_sha256:
            raise InputEvidenceOriginPackError(
                "authenticated request payload evidence checksum diverged"
            )
        origin_class = report_item.get("origin_class")
        if origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackError(
                "authenticated request returned unsupported origin_class"
            )
        manifest_items.append(
            {
                "program_evidence_binding": {
                    "workstream_id": payload.workstream_id,
                    "role": payload.role,
                    "sha256": payload.evidence_sha256,
                },
                "origin_class": origin_class,
                "evidence_artifact": _binding(
                    path=paths["evidence"], raw=payload.evidence_bytes, role="evidence"
                ),
                "origin_declaration_artifact": _binding(
                    path=paths["origin_declaration"],
                    raw=payload.origin_declaration_bytes,
                    role="origin_declaration",
                ),
                "origin_verification_decision_artifact": _binding(
                    path=paths["origin_verification_decision"],
                    raw=payload.origin_verification_decision_bytes,
                    role="origin_verification_decision",
                ),
            }
        )

    manifest = {
        "schema_version": INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION,
        "pack_policy_version": INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION,
        "publication_platform": publication_platform,
        "supported_publication_platforms": list(
            INPUT_EVIDENCE_ORIGIN_PACK_SUPPORTED_PLATFORMS
        ),
        "request_artifact": _binding(
            path=_REQUEST_SNAPSHOT, raw=authenticated.request_bytes
        ),
        "items": manifest_items,
        "request_source_path_authoritative": False,
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
    manifest_bytes = _canonical_json_bytes(manifest)
    payloads[_PACK_MANIFEST] = manifest_bytes

    output.parent.mkdir(parents=True, exist_ok=True)
    build_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    published = False
    try:
        for relative, raw in payloads.items():
            _write_payload(build_root, relative, raw)
        _validate_written_payloads(build_root, payloads)
        # A second pass closes simple mutation hooks between validation and publication.
        _validate_written_payloads(build_root, payloads)
        _atomic_publish_no_replace(build_root, output)
        published = True
    finally:
        if not published and build_root.exists():
            import shutil

            shutil.rmtree(build_root, ignore_errors=True)

    return {
        "schema_version": INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION,
        "pack_policy_version": INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION,
        "output_dir": str(output),
        "manifest_binding": {
            "path": _PACK_MANIFEST,
            "sha256": _sha256(manifest_bytes),
            "size_bytes": len(manifest_bytes),
        },
        "request_source": {
            "path": str(request_source),
            "authoritative": False,
        },
        "item_count": len(manifest_items),
        "empirical_authority_granted": False,
        "scientific_status_changed": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }


__all__ = [
    "INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION",
    "INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION",
    "INPUT_EVIDENCE_ORIGIN_PACK_SUPPORTED_PLATFORMS",
    "InputEvidenceOriginPackError",
    "publish_input_evidence_origin_pack",
]
