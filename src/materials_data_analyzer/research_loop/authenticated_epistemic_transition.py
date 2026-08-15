"""Atomic, self-contained producer for authenticated directional inference provenance.

The producer authenticates exact proposal/verifier bytes and exact inference-edge identity,
but deliberately publishes the directional edge as *diagnostic*. Scientific authority is
left to a later consumer that independently re-authenticates the published bundle.

Filesystem trust boundary: atomic publication and staged integrity checks assume this process
has exclusive write ownership of its private staging tree from creation through publication.
The producer is not a sandbox against a hostile process sharing the same OS identity and write
access to that staging parent. No provenance or security claim should be read as resisting such
a same-identity attacker. Atomic publication for this producer is currently supported only on
Windows and Linux; other platforms fail closed before transition inputs are consumed.
"""

from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .authenticated_inference_binding import (
    DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
    AuthenticatedInferenceBindingError,
    authenticate_inference_binding,
)
from .epistemic_graph import evaluate_epistemic_graph, validate_epistemic_graph
from .epistemic_transition import (
    TRANSITION_POLICY_VERSION,
    TRANSITION_SCHEMA_VERSION,
    EpistemicTransitionError,
    _assessment_for,
    _canonical_json_bytes,
    _read_json_snapshot,
    validate_transition_proposal,
    validate_verification_decision,
)
from .epistemic_transition import (
    VERIFICATION_SCHEMA_VERSION as LEGACY_VERIFICATION_SCHEMA_VERSION,
)

AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.6"
AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION = "1.0"
AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE = "authenticated_domain_verification_decision"
AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS = ("linux", "windows")


class AuthenticatedEpistemicTransitionError(EpistemicTransitionError):
    """Raised when authenticated transition production cannot preserve provenance."""


def _require_supported_publication_platform(
    *,
    os_name: str | None = None,
    platform: str | None = None,
) -> str:
    actual_os_name = os.name if os_name is None else os_name
    actual_platform = sys.platform if platform is None else platform
    if actual_os_name == "nt":
        return "windows"
    if actual_platform.startswith("linux"):
        return "linux"
    raise AuthenticatedEpistemicTransitionError(
        "authenticated transition publication currently supports only Windows and Linux "
        "because another platform-safe atomic no-replace directory primitive has not been "
        "implemented"
    )


def _legacy_scope_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    legacy = dict(value)
    legacy.pop("inference_edge_id", None)
    legacy["schema_version"] = LEGACY_VERIFICATION_SCHEMA_VERSION
    return legacy


def _target_assessment(result: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    assessment = _assessment_for(result, node_id)
    if assessment is None:
        raise AuthenticatedEpistemicTransitionError(
            "target assessment could not be reconstructed"
        )
    return assessment


def _diagnostic_edge_ids(assessment: Mapping[str, Any]) -> set[str]:
    values = assessment.get("diagnostic_relation_edges")
    if not isinstance(values, list):
        raise AuthenticatedEpistemicTransitionError(
            "target assessment diagnostic_relation_edges must be a list"
        )
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise AuthenticatedEpistemicTransitionError(
                "target assessment diagnostic_relation_edges must contain non-empty edge IDs"
            )
        result.add(value)
    return result


def _bundle_path(*parts: str) -> str:
    return Path(*parts).as_posix()


def _safe_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if (
        suffix.startswith(".")
        and len(suffix) <= 16
        and suffix[1:]
        and suffix[1:].isalnum()
    ):
        return suffix
    return ""


def _resolve_file(path_value: object, *, artifact_root: Path, field: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise AuthenticatedEpistemicTransitionError(f"{field} must be non-empty text")
    candidate = Path(path_value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} could not be resolved: {candidate}"
        ) from exc
    if not resolved.is_file():
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must resolve to a regular file: {resolved}"
        )
    return resolved


def _read_bound_file(
    *,
    path_value: object,
    expected_sha256: object,
    artifact_root: Path,
    field: str,
) -> tuple[Path, bytes, str]:
    if not isinstance(expected_sha256, str) or not expected_sha256.strip():
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.sha256 must be non-empty text"
        )
    source = _resolve_file(path_value, artifact_root=artifact_root, field=f"{field}.path")
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} became unreadable: {source}"
        ) from exc
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha256.strip():
        raise AuthenticatedEpistemicTransitionError(
            f"{field} checksum mismatch: expected {expected_sha256}, got {actual_sha}"
        )
    return source, data, actual_sha


def _add_payload(payloads: dict[str, bytes], path: str, data: bytes) -> None:
    if path in payloads:
        raise AuthenticatedEpistemicTransitionError(
            f"duplicate bundle snapshot path: {path}"
        )
    payloads[path] = data


def _snapshot_binding(
    *,
    source: Path,
    path: str,
    sha256: str,
    role: str | None = None,
    size_bytes: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "source_path": str(source),
        "source_path_authoritative": False,
        "sha256": sha256,
    }
    if role is not None:
        result["role"] = role
    if size_bytes is not None:
        result["size_bytes"] = size_bytes
    return result


def _lineage_records(
    metadata: Mapping[str, Any], *, field: str
) -> list[Mapping[str, Any]]:
    raw = metadata.get(field, [])
    if not isinstance(raw, list):
        raise AuthenticatedEpistemicTransitionError(
            f"base graph metadata.{field} must be a list"
        )
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field}[{index}] must be an object"
            )
        raw_transition_id = item.get("transition_id")
        if not isinstance(raw_transition_id, str) or not raw_transition_id.strip():
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field}[{index}].transition_id must be non-empty text"
            )
        transition_id = raw_transition_id.strip()
        if transition_id in seen:
            raise AuthenticatedEpistemicTransitionError(
                f"base graph metadata.{field} contains duplicate transition_id: {transition_id}"
            )
        seen.add(transition_id)
        result.append(item)
    return result


def _lineage_identity(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AuthenticatedEpistemicTransitionError(
            f"lineage coherence field {field} must be non-empty text"
        )
    return value.strip()


def _lineage_sha256(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if (
        not isinstance(value, str)
        or value != value.strip()
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"lineage coherence field {field} must be canonical lowercase SHA-256 text"
        )
    return value


def _assert_cross_lineage_coherence(
    legacy: list[Mapping[str, Any]], authenticated: list[Mapping[str, Any]]
) -> None:
    """Reject one normalized transition identity denoting incompatible histories."""
    legacy_by_id = {
        _lineage_identity(item, "transition_id"): item for item in legacy
    }
    authenticated_by_id = {
        _lineage_identity(item, "transition_id"): item for item in authenticated
    }
    for transition_id in sorted(set(legacy_by_id) & set(authenticated_by_id)):
        legacy_record = legacy_by_id[transition_id]
        auth_record = authenticated_by_id[transition_id]
        base_artifact = auth_record.get("base_graph_artifact")
        proposal_artifact = auth_record.get("proposal_artifact")
        verifier_artifact = auth_record.get("verification_decision_artifact")
        binding = auth_record.get("authenticated_inference_binding")
        if not all(
            isinstance(item, Mapping)
            for item in (base_artifact, proposal_artifact, verifier_artifact, binding)
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"cross-lineage transition_id {transition_id} lacks authenticated coherence fields"
            )
        assert isinstance(base_artifact, Mapping)
        assert isinstance(proposal_artifact, Mapping)
        assert isinstance(verifier_artifact, Mapping)
        assert isinstance(binding, Mapping)
        expected_pairs = (
            (
                _lineage_sha256(legacy_record, "parent_graph_sha256"),
                _lineage_sha256(base_artifact, "sha256"),
            ),
            (
                _lineage_sha256(legacy_record, "proposal_sha256"),
                _lineage_sha256(proposal_artifact, "sha256"),
            ),
            (
                _lineage_sha256(legacy_record, "verification_decision_sha256"),
                _lineage_sha256(verifier_artifact, "sha256"),
            ),
            (
                _lineage_identity(legacy_record, "result_node_id"),
                _lineage_identity(binding, "result_node_id"),
            ),
            (transition_id, _lineage_identity(binding, "transition_id")),
        )
        if any(left != right for left, right in expected_pairs):
            raise AuthenticatedEpistemicTransitionError(
                f"cross-lineage transition_id {transition_id} denotes incompatible histories"
            )


def _reject_transition_id_reuse(
    metadata: Mapping[str, Any], *, transition_id: str
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    legacy = _lineage_records(metadata, field="transition_lineage")
    authenticated = _lineage_records(
        metadata, field="authenticated_transition_lineage"
    )
    _assert_cross_lineage_coherence(legacy, authenticated)
    if any(str(item.get("transition_id")).strip() == transition_id for item in legacy):
        raise AuthenticatedEpistemicTransitionError(
            f"transition_id already exists in base transition_lineage: {transition_id}"
        )
    if any(
        str(item.get("transition_id")).strip() == transition_id
        for item in authenticated
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"transition_id already exists in base authenticated_transition_lineage: {transition_id}"
        )
    return legacy, authenticated


def _snapshot_graph_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
) -> tuple[dict[str, str], dict[str, Any]]:
    role = raw.get("role")
    if not isinstance(role, str) or not role.strip():
        raise AuthenticatedEpistemicTransitionError(f"{field}.role is malformed")
    source, data, actual_sha = _read_bound_file(
        path_value=raw.get("path"),
        expected_sha256=raw.get("sha256"),
        artifact_root=artifact_root,
        field=field,
    )
    _add_payload(payloads, bundle_path, data)
    graph_binding = {
        "role": role.strip(),
        "path": bundle_path,
        "sha256": actual_sha,
    }
    provenance = _snapshot_binding(
        source=source,
        path=bundle_path,
        sha256=actual_sha,
        role=role.strip(),
        size_bytes=len(data),
    )
    return graph_binding, provenance


def _snapshot_lineage_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
) -> dict[str, Any]:
    source, data, actual_sha = _read_bound_file(
        path_value=raw.get("path"),
        expected_sha256=raw.get("sha256"),
        artifact_root=artifact_root,
        field=field,
    )
    _add_payload(payloads, bundle_path, data)
    copied = dict(raw)
    copied["path"] = bundle_path
    copied["source_path"] = (
        raw.get("source_path")
        if isinstance(raw.get("source_path"), str) and raw.get("source_path")
        else str(source)
    )
    copied["source_path_authoritative"] = False
    copied["sha256"] = actual_sha
    copied["size_bytes"] = len(data)
    return copied


def _captured_lineage_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
) -> tuple[dict[str, Any], bytes]:
    expected_sha = _lineage_sha256(raw, "sha256")
    source, data, actual_sha = _read_bound_file(
        path_value=raw.get("path"),
        expected_sha256=expected_sha,
        artifact_root=artifact_root,
        field=field,
    )
    _add_payload(payloads, bundle_path, data)
    copied = dict(raw)
    copied["path"] = bundle_path
    copied["source_path"] = (
        raw.get("source_path")
        if isinstance(raw.get("source_path"), str) and raw.get("source_path")
        else str(source)
    )
    copied["source_path_authoritative"] = False
    copied["sha256"] = actual_sha
    copied["size_bytes"] = len(data)
    return copied, data


def _proposal_result_artifact_identity(proposal_bytes: bytes) -> dict[str, str]:
    # Exact-byte JSON validity and duplicate-key rejection already succeeded in
    # authenticate_inference_binding before this helper is called.
    try:
        proposal = json.loads(proposal_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # defensive only
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal could not be reparsed"
        ) from exc
    if not isinstance(proposal, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal root must be an object"
        )
    result_node = proposal.get("result_node")
    if not isinstance(result_node, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result_node must be an object"
        )
    bindings = result_node.get("artifact_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inherited proposal result artifacts must be non-empty"
        )
    identity: dict[str, str] = {}
    for index, raw in enumerate(bindings):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inherited proposal result artifact must be an object"
            )
        role = _lineage_identity(raw, "role")
        if role in identity:
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inherited proposal result artifact roles must be unique"
            )
        identity[role] = _lineage_sha256(raw, "sha256")
    return identity


def _remap_authenticated_lineage_artifacts(
    metadata: dict[str, Any],
    *,
    artifact_root: Path,
    payloads: dict[str, bytes],
) -> None:
    raw_lineage = metadata.get("authenticated_transition_lineage", [])
    if not isinstance(raw_lineage, list):
        raise AuthenticatedEpistemicTransitionError(
            "base graph metadata.authenticated_transition_lineage must be a list"
        )
    remapped: list[dict[str, Any]] = []
    for index, raw_record in enumerate(raw_lineage):
        if not isinstance(raw_record, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] must be an object"
            )
        record = copy.deepcopy(dict(raw_record))
        if record.get("schema_version") != AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].schema_version must be "
                f"{AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION}"
            )
        stored_binding = record.get("authenticated_inference_binding")
        if not isinstance(stored_binding, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].authenticated_inference_binding "
                "must be an object"
            )
        record_transition_id = _lineage_identity(record, "transition_id")
        if _lineage_identity(stored_binding, "transition_id") != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] transition identity is inconsistent"
            )
        if record.get("scientific_authority_applied") is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].scientific_authority_applied "
                "must be false for producer lineage"
            )

        captured: dict[str, tuple[dict[str, Any], bytes]] = {}
        for name in (
            "base_graph_artifact",
            "proposal_artifact",
            "verification_decision_artifact",
        ):
            raw_binding = record.get(name)
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    f"authenticated_transition_lineage[{index}].{name} must be an object"
                )
            if (
                name == "verification_decision_artifact"
                and raw_binding.get("role") != AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE
            ):
                raise AuthenticatedEpistemicTransitionError(
                    f"authenticated_transition_lineage[{index}].{name}.role must be "
                    f"{AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE}"
                )
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"authenticated_transition_lineage[{index}].{name}.path",
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                f"{name}{_safe_suffix(suffix_source)}",
            )
            captured[name] = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"authenticated_transition_lineage[{index}].{name}",
                payloads=payloads,
            )

        base_binding, _base_bytes = captured["base_graph_artifact"]
        proposal_binding, proposal_bytes = captured["proposal_artifact"]
        verifier_binding, verifier_bytes = captured["verification_decision_artifact"]
        try:
            recomputed_binding = authenticate_inference_binding(
                proposal_bytes=proposal_bytes,
                verification_decision_bytes=verifier_bytes,
                expected_base_graph_sha256=_lineage_sha256(base_binding, "sha256"),
            )
        except AuthenticatedInferenceBindingError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] exact inference binding "
                "could not be re-authenticated"
            ) from exc
        if dict(stored_binding) != recomputed_binding:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] stored inference binding "
                "does not match exact proposal/verifier bytes"
            )
        if recomputed_binding["transition_id"] != record_transition_id:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] recomputed transition identity "
                "is inconsistent"
            )
        if recomputed_binding["proposal_sha256"] != _lineage_sha256(
            proposal_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] proposal binding is inconsistent"
            )
        if recomputed_binding["verification_decision_sha256"] != _lineage_sha256(
            verifier_binding, "sha256"
        ):
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] verifier binding is inconsistent"
            )

        expected_results = _proposal_result_artifact_identity(proposal_bytes)
        raw_results = record.get("result_artifact_snapshots")
        if not isinstance(raw_results, list) or not raw_results:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}].result_artifact_snapshots "
                "must be a non-empty list"
            )
        result_records: list[dict[str, Any]] = []
        actual_results: dict[str, str] = {}
        for result_index, raw_binding in enumerate(raw_results):
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    "authenticated lineage result artifact snapshot must be an object"
                )
            role = _lineage_identity(raw_binding, "role")
            if role in actual_results:
                raise AuthenticatedEpistemicTransitionError(
                    "authenticated lineage result artifact roles must be unique"
                )
            expected_sha = _lineage_sha256(raw_binding, "sha256")
            suffix_source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=(
                    f"authenticated_transition_lineage[{index}]"
                    f".result_artifact_snapshots[{result_index}].path"
                ),
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"lineage-{index:03d}",
                "result_artifacts",
                f"result-{result_index:03d}{_safe_suffix(suffix_source)}",
            )
            copied, _data = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=(
                    f"authenticated_transition_lineage[{index}]"
                    f".result_artifact_snapshots[{result_index}]"
                ),
                payloads=payloads,
            )
            actual_results[role] = expected_sha
            result_records.append(copied)
        if actual_results != expected_results:
            raise AuthenticatedEpistemicTransitionError(
                f"authenticated_transition_lineage[{index}] result snapshots do not match "
                "the exact proposal result artifacts"
            )

        record["base_graph_artifact"] = base_binding
        record["proposal_artifact"] = proposal_binding
        record["verification_decision_artifact"] = verifier_binding
        record["result_artifact_snapshots"] = result_records
        record["authenticated_inference_binding"] = dict(recomputed_binding)
        remapped.append(record)
    metadata["authenticated_transition_lineage"] = remapped


def _remap_base_graph_artifacts(
    base_graph: Mapping[str, Any],
    *,
    artifact_root: Path,
    payloads: dict[str, bytes],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    graph = copy.deepcopy(dict(base_graph))
    inherited_provenance: list[dict[str, Any]] = []

    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list):
        raise AuthenticatedEpistemicTransitionError("base graph nodes must be a list")
    for node_index, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            continue
        if node.get("node_type") == "evidence":
            raise AuthenticatedEpistemicTransitionError(
                "authenticated self-contained transition does not yet accept inherited "
                "evidence nodes because evidence_binding lacks a first-class checksum-bound "
                "resolvable artifact contract"
            )
        raw_bindings = node.get("artifact_bindings")
        if not isinstance(raw_bindings, list):
            continue
        new_bindings: list[dict[str, str]] = []
        for artifact_index, raw_binding in enumerate(raw_bindings):
            if not isinstance(raw_binding, Mapping):
                raise AuthenticatedEpistemicTransitionError(
                    "base graph node artifact binding must be an object"
                )
            source = _resolve_file(
                raw_binding.get("path"),
                artifact_root=artifact_root,
                field=f"base.nodes[{node_index}].artifact_bindings[{artifact_index}].path",
            )
            relative = _bundle_path(
                "provenance",
                "inherited",
                f"node-{node_index:03d}",
                f"artifact-{artifact_index:03d}{_safe_suffix(source)}",
            )
            binding, provenance = _snapshot_graph_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"base.nodes[{node_index}].artifact_bindings[{artifact_index}]",
                payloads=payloads,
            )
            new_bindings.append(binding)
            inherited_provenance.append(
                {
                    "binding_type": "node_artifact",
                    "node_id": node.get("node_id"),
                    **provenance,
                }
            )
        node["artifact_bindings"] = new_bindings

    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        raise AuthenticatedEpistemicTransitionError("base graph edges must be a list")
    for edge_index, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            continue
        raw_binding = edge.get("verification_artifact")
        if not isinstance(raw_binding, Mapping):
            continue
        source = _resolve_file(
            raw_binding.get("path"),
            artifact_root=artifact_root,
            field=f"base.edges[{edge_index}].verification_artifact.path",
        )
        relative = _bundle_path(
            "provenance",
            "inherited",
            f"edge-{edge_index:03d}",
            f"verification{_safe_suffix(source)}",
        )
        binding, provenance = _snapshot_graph_binding(
            raw_binding,
            artifact_root=artifact_root,
            bundle_path=relative,
            field=f"base.edges[{edge_index}].verification_artifact",
            payloads=payloads,
        )
        edge["verification_artifact"] = binding
        inherited_provenance.append(
            {
                "binding_type": "edge_verification_artifact",
                "edge_id": edge.get("edge_id"),
                **provenance,
            }
        )

    metadata = graph.get("metadata")
    if metadata is None:
        metadata = {}
        graph["metadata"] = metadata
    if not isinstance(metadata, dict):
        raise AuthenticatedEpistemicTransitionError("base graph metadata must be an object")
    _remap_authenticated_lineage_artifacts(
        metadata,
        artifact_root=artifact_root,
        payloads=payloads,
    )
    return graph, inherited_provenance


def _prepare_current_result_snapshots(
    proposal: Mapping[str, Any],
    *,
    payloads: dict[str, bytes],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    raw_result = proposal.get("result_node")
    if not isinstance(raw_result, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal result_node is malformed"
        )
    raw_bindings = raw_result.get("artifact_bindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal result artifact bindings are malformed"
        )
    graph_bindings: list[dict[str, str]] = []
    provenance: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}] must be an object"
            )
        path_value = raw.get("path")
        if not isinstance(path_value, str):
            raise AuthenticatedEpistemicTransitionError(
                f"validated result artifact binding[{index}].path is malformed"
            )
        source = Path(path_value).expanduser().resolve(strict=True)
        relative = _bundle_path(
            "provenance",
            "current",
            "result_artifacts",
            f"result-{index:03d}{_safe_suffix(source)}",
        )
        binding, record = _snapshot_graph_binding(
            raw,
            artifact_root=source.parent,
            bundle_path=relative,
            field=f"validated result artifact binding[{index}]",
            payloads=payloads,
        )
        graph_bindings.append(binding)
        provenance.append(record)
    return graph_bindings, provenance


def _proposal_result_and_edges(
    proposal: Mapping[str, Any],
    *,
    result_artifact_bindings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inference = proposal.get("proposed_inference")
    raw_result = proposal.get("result_node")
    source_action = proposal.get("source_action")
    input_evidence = proposal.get("input_evidence_bindings")
    limitations = proposal.get("limitations")
    if not isinstance(inference, Mapping) or not isinstance(raw_result, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal inference/result node is malformed"
        )
    if not isinstance(source_action, Mapping):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal source_action is malformed"
        )
    if not isinstance(input_evidence, list) or not isinstance(limitations, list):
        raise AuthenticatedEpistemicTransitionError(
            "validated proposal evidence/limitations are malformed"
        )

    result_node = dict(raw_result)
    result_node["artifact_bindings"] = [dict(item) for item in result_artifact_bindings]
    result_metadata = dict(result_node.get("metadata", {}))
    result_metadata["source_action"] = dict(source_action)
    result_metadata["input_evidence_bindings"] = list(input_evidence)
    result_metadata["transition_id"] = proposal["transition_id"]
    result_metadata["limitations"] = list(limitations)
    result_node["metadata"] = result_metadata

    tests_edge = {
        "edge_id": inference["tests_edge_id"],
        "source_node_id": result_node["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": "tests",
        "assessment_level": "proposal",
        "rationale": (
            "The completed result was introduced to test this target; execution success alone "
            "does not establish scientific support, contradiction, or falsification."
        ),
        "active": True,
    }
    inference_edge = {
        "edge_id": inference["inference_edge_id"],
        "source_node_id": result_node["node_id"],
        "target_node_id": proposal["target_node_id"],
        "relation": inference["relation"],
        "assessment_level": "diagnostic",
        "rationale": inference["rationale"],
        "active": True,
    }
    return result_node, tests_edge, inference_edge


def _write_payloads(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, data in payloads.items():
        destination = root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def _is_reparse_point(info: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(marker and (getattr(info, "st_file_attributes", 0) & marker))


def _read_fd_bytes(fd: int, *, field: str) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must be a regular staged file"
        )
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _read_staged_regular_file_posix(
    root: Path, relative: Path, *, field: str
) -> bytes:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    current_fd = root_fd
    try:
        for component in relative.parts[:-1]:
            try:
                next_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=current_fd,
                )
            except OSError as exc:
                raise AuthenticatedEpistemicTransitionError(
                    f"{field} contains an unsafe staged parent component"
                ) from exc
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        try:
            fd = os.open(relative.name, file_flags, dir_fd=current_fd)
        except OSError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} could not be opened as a no-follow staged file"
            ) from exc
        try:
            return _read_fd_bytes(fd, field=field)
        finally:
            os.close(fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _read_staged_regular_file_portable(
    root: Path, relative: Path, *, field: str
) -> bytes:
    current = root
    try:
        root_info = os.lstat(root)
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root could not be inspected"
        ) from exc
    if stat.S_ISLNK(root_info.st_mode) or _is_reparse_point(root_info):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root must not be a link or reparse point"
        )
    if not stat.S_ISDIR(root_info.st_mode):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staging root must be a directory"
        )
    for index, component in enumerate(relative.parts):
        current = current / component
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged path could not be inspected"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged path must not contain links or reparse points"
            )
        is_last = index == len(relative.parts) - 1
        if not is_last and not stat.S_ISDIR(info.st_mode):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} staged parent must be a directory"
            )
        if is_last and not stat.S_ISREG(info.st_mode):
            raise AuthenticatedEpistemicTransitionError(
                f"{field} must be a regular staged file"
            )
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(current, flags)
    except OSError as exc:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} staged file could not be opened"
        ) from exc
    try:
        return _read_fd_bytes(fd, field=field)
    finally:
        os.close(fd)


def _read_staged_regular_file(root: Path, relative: str, *, field: str) -> bytes:
    """Read one staged file without accepting linked path components."""
    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must use a normalized bundle-relative staged path"
        )
    if (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
    ):
        return _read_staged_regular_file_posix(root, relative_path, field=field)
    return _read_staged_regular_file_portable(root, relative_path, field=field)


def _validate_written_payloads(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, expected in payloads.items():
        actual = _read_staged_regular_file(
            root,
            relative,
            field=f"published snapshot {relative}",
        )
        if actual != expected:
            raise AuthenticatedEpistemicTransitionError(
                f"published snapshot bytes changed before atomic publication: {relative}"
            )


def _validate_written_bundle(
    root: Path,
    *,
    graph_bytes: bytes,
    manifest_bytes: bytes,
    payloads: Mapping[str, bytes],
    program_state: Mapping[str, Any],
    target_node_id: str,
    inference_edge_id: str,
) -> dict[str, Any]:
    _validate_written_payloads(root, payloads)
    graph_raw = _read_staged_regular_file(
        root, "epistemic_graph.json", field="written epistemic graph"
    )
    manifest_raw = _read_staged_regular_file(
        root,
        "epistemic_transition_manifest.json",
        field="written transition manifest",
    )
    if graph_raw != graph_bytes:
        raise AuthenticatedEpistemicTransitionError(
            "written epistemic graph bytes changed before atomic publication"
        )
    if manifest_raw != manifest_bytes:
        raise AuthenticatedEpistemicTransitionError(
            "written transition manifest bytes changed before atomic publication"
        )
    graph, _, _ = _read_json_snapshot(root / "epistemic_graph.json")
    evaluation = evaluate_epistemic_graph(
        graph,
        program_state=program_state,
        artifact_root=root,
    )
    target_after = _target_assessment(evaluation, target_node_id)
    if inference_edge_id not in _diagnostic_edge_ids(target_after):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated inference edge was not preserved as a diagnostic relation"
        )
    # Re-read all files after graph evaluation so a staging hook cannot substitute a
    # payload during evaluation and leave altered bytes for publication.
    _validate_written_payloads(root, payloads)
    if _read_staged_regular_file(
        root, "epistemic_graph.json", field="written epistemic graph"
    ) != graph_bytes:
        raise AuthenticatedEpistemicTransitionError(
            "written epistemic graph changed during final bundle validation"
        )
    if _read_staged_regular_file(
        root,
        "epistemic_transition_manifest.json",
        field="written transition manifest",
    ) != manifest_bytes:
        raise AuthenticatedEpistemicTransitionError(
            "written transition manifest changed during final bundle validation"
        )
    return target_after


def _atomic_publish_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing an existing destination."""
    if os.name == "nt":
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise AuthenticatedEpistemicTransitionError(
                f"output_dir appeared during atomic publication: {destination}"
            ) from exc
        except OSError as exc:
            if destination.exists():
                raise AuthenticatedEpistemicTransitionError(
                    f"output_dir appeared during atomic publication: {destination}"
                ) from exc
            raise
        return

    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise AuthenticatedEpistemicTransitionError(
                "atomic no-replace directory publication requires renameat2 on Linux"
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        rc = renameat2(
            -100,
            os.fsencode(source),
            -100,
            os.fsencode(destination),
            1,
        )
        if rc != 0:
            error = ctypes.get_errno()
            if error in {errno.EEXIST, errno.ENOTEMPTY}:
                raise AuthenticatedEpistemicTransitionError(
                    f"output_dir appeared during atomic publication: {destination}"
                )
            raise AuthenticatedEpistemicTransitionError(
                f"atomic no-replace publication failed with errno {error}"
            )
        return

    raise AuthenticatedEpistemicTransitionError(
        "authenticated transition publication is unsupported on this platform because "
        "an atomic no-replace directory primitive is unavailable"
    )


def apply_authenticated_epistemic_transition_files(
    *,
    base_graph_path: str | Path,
    proposal_path: str | Path,
    verification_decision_path: str | Path,
    program_state: Mapping[str, Any],
    artifact_root: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Produce an authenticated diagnostic bundle under exclusive staging ownership.

    The filesystem integrity boundary assumes no hostile same-OS-identity process can write
    into or replace this function's private staging tree while it is being assembled.
    Publication is intentionally limited to Windows and Linux until another platform-safe
    atomic no-replace directory primitive is implemented.
    """
    publication_platform = _require_supported_publication_platform()
    base_path = Path(base_graph_path).expanduser().resolve(strict=True)
    proposal_file = Path(proposal_path).expanduser().resolve(strict=True)
    verification_file = Path(verification_decision_path).expanduser().resolve(strict=True)
    artifacts = Path(artifact_root).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise AuthenticatedEpistemicTransitionError(
            f"output_dir must not already exist: {output}"
        )
    if not artifacts.is_dir():
        raise AuthenticatedEpistemicTransitionError(
            f"artifact_root must be a directory: {artifacts}"
        )

    base_raw, base_bytes, base_sha = _read_json_snapshot(base_path)
    proposal_raw, proposal_bytes, proposal_sha = _read_json_snapshot(proposal_file)
    verification_raw, verification_bytes, verification_sha = _read_json_snapshot(
        verification_file
    )
    if verification_raw.get("schema_version") != DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated transition requires verification decision schema v1.1"
        )

    try:
        authenticated_binding = authenticate_inference_binding(
            proposal_bytes=proposal_bytes,
            verification_decision_bytes=verification_bytes,
            expected_base_graph_sha256=base_sha,
        )
    except AuthenticatedInferenceBindingError as exc:
        raise AuthenticatedEpistemicTransitionError(str(exc)) from exc

    base_validated = validate_epistemic_graph(
        base_raw,
        program_state=program_state,
        artifact_root=artifacts,
    )
    before_eval = evaluate_epistemic_graph(
        base_raw,
        program_state=program_state,
        artifact_root=artifacts,
    )
    proposal = validate_transition_proposal(
        proposal_raw,
        base_graph=base_validated,
        base_graph_sha256=base_sha,
        program_state=program_state,
        artifact_root=artifacts,
    )
    if authenticated_binding["transition_id"] != proposal["transition_id"]:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated verifier transition_id does not match validated proposal"
        )
    scope_validation = validate_verification_decision(
        _legacy_scope_decision(verification_raw),
        proposal=proposal,
        proposal_sha256=proposal_sha,
        verification_sha256=verification_sha,
    )
    if scope_validation["inference_scope"] != authenticated_binding["inference_scope"]:
        raise AuthenticatedEpistemicTransitionError(
            "authenticated verifier scope diverged from transition scope validation"
        )
    if scope_validation["inference_scope"] == "empirical_derived":
        raise AuthenticatedEpistemicTransitionError(
            "authenticated self-contained transition does not yet accept empirical_derived "
            "inference because program evidence bindings do not provide a first-class "
            "checksum-bound resolvable artifact contract"
        )

    metadata = base_raw.get("metadata")
    metadata_mapping: Mapping[str, Any] = metadata if isinstance(metadata, Mapping) else {}
    transition_id = str(proposal["transition_id"])
    legacy_lineage, authenticated_lineage = _reject_transition_id_reuse(
        metadata_mapping,
        transition_id=transition_id,
    )

    payloads: dict[str, bytes] = {}
    remapped_base, inherited_provenance = _remap_base_graph_artifacts(
        base_raw,
        artifact_root=artifacts,
        payloads=payloads,
    )
    remapped_metadata = remapped_base.get("metadata")
    if not isinstance(remapped_metadata, dict):
        raise AuthenticatedEpistemicTransitionError(
            "remapped base graph metadata must be an object"
        )

    base_snapshot_path = _bundle_path("provenance", "current", "base_graph.json")
    proposal_snapshot_path = _bundle_path("provenance", "current", "proposal.json")
    verification_snapshot_path = _bundle_path(
        "provenance", "current", "verification_decision.json"
    )
    _add_payload(payloads, base_snapshot_path, base_bytes)
    _add_payload(payloads, proposal_snapshot_path, proposal_bytes)
    _add_payload(payloads, verification_snapshot_path, verification_bytes)
    base_binding = _snapshot_binding(
        source=base_path,
        path=base_snapshot_path,
        sha256=base_sha,
        size_bytes=len(base_bytes),
    )
    proposal_binding = _snapshot_binding(
        source=proposal_file,
        path=proposal_snapshot_path,
        sha256=proposal_sha,
        size_bytes=len(proposal_bytes),
    )
    verification_binding = _snapshot_binding(
        source=verification_file,
        path=verification_snapshot_path,
        sha256=verification_sha,
        role=AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE,
        size_bytes=len(verification_bytes),
    )

    result_bindings, result_provenance = _prepare_current_result_snapshots(
        proposal,
        payloads=payloads,
    )
    result_node, tests_edge, inference_edge = _proposal_result_and_edges(
        proposal,
        result_artifact_bindings=result_bindings,
    )
    edge_id = str(authenticated_binding["inference_edge_id"])
    if inference_edge["edge_id"] != edge_id:
        raise AuthenticatedEpistemicTransitionError(
            "constructed inference edge does not match authenticated inference edge ID"
        )

    remapped_metadata["transition_lineage"] = [
        *legacy_lineage,
        {
            "transition_id": transition_id,
            "parent_graph_id": base_validated["graph_id"],
            "parent_graph_sha256": base_sha,
            "proposal_sha256": proposal_sha,
            "verification_decision_sha256": verification_sha,
            "result_node_id": result_node["node_id"],
        },
    ]
    inherited_authenticated = remapped_metadata.get("authenticated_transition_lineage", [])
    if not isinstance(inherited_authenticated, list):
        raise AuthenticatedEpistemicTransitionError(
            "remapped authenticated_transition_lineage must be a list"
        )
    if len(inherited_authenticated) != len(authenticated_lineage):
        raise AuthenticatedEpistemicTransitionError(
            "authenticated lineage changed cardinality during artifact remapping"
        )
    remapped_metadata["authenticated_transition_lineage"] = [
        *inherited_authenticated,
        {
            "schema_version": AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION,
            "transition_id": transition_id,
            "base_graph_artifact": base_binding,
            "proposal_artifact": proposal_binding,
            "verification_decision_artifact": verification_binding,
            "result_artifact_snapshots": result_provenance,
            "authenticated_inference_binding": dict(authenticated_binding),
            "scientific_authority_applied": False,
        },
    ]

    successor = {
        "schema_version": remapped_base["schema_version"],
        "graph_id": proposal["new_graph_id"],
        "research_scope": remapped_base["research_scope"],
        "nodes": [*remapped_base["nodes"], result_node],
        "edges": [*remapped_base["edges"], tests_edge, inference_edge],
        "metadata": remapped_metadata,
    }
    target_id = str(proposal["target_node_id"])
    before_target = _target_assessment(before_eval, target_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    build_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    published = False
    try:
        _write_payloads(build_root, payloads)
        evaluation = evaluate_epistemic_graph(
            successor,
            program_state=program_state,
            artifact_root=build_root,
        )
        target_after = _target_assessment(evaluation, target_id)
        if edge_id not in _diagnostic_edge_ids(target_after):
            raise AuthenticatedEpistemicTransitionError(
                "authenticated inference edge did not remain diagnostic before consumer verification"
            )

        graph_bytes = _canonical_json_bytes(successor)
        graph_sha = hashlib.sha256(graph_bytes).hexdigest()
        manifest = {
            "schema_version": TRANSITION_SCHEMA_VERSION,
            "transition_policy_version": TRANSITION_POLICY_VERSION,
            "authenticated_transition_policy_version": AUTHENTICATED_TRANSITION_POLICY_VERSION,
            "transition_id": transition_id,
            "bundle_artifact_root": ".",
            "publication_platform": publication_platform,
            "supported_publication_platforms": list(
                AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS
            ),
            "base_graph_binding": base_binding,
            "proposal_binding": proposal_binding,
            "verification_decision_binding": verification_binding,
            "authenticated_inference_binding": dict(authenticated_binding),
            "inherited_artifact_snapshots": inherited_provenance,
            "result_artifact_bindings": result_bindings,
            "result_artifact_provenance": result_provenance,
            "successor_graph": {
                "graph_id": successor["graph_id"],
                "path": "epistemic_graph.json",
                "sha256": graph_sha,
            },
            "target_node_id": target_id,
            "target_before": before_target,
            "target_after": target_after,
            "inference_assessment_level": "diagnostic",
            "domain_verification_decision_authenticated": True,
            "scientific_authority_applied": False,
            "verification": {
                **scope_validation,
                "schema_version": DOMAIN_VERIFICATION_DECISION_SCHEMA_VERSION,
                "inference_edge_id": edge_id,
                "verification_sha256": verification_sha,
            },
            "autonomy_boundary": {
                "action_execution_performed": False,
                "network_access_performed": False,
                "physical_experiment_execution_performed": False,
                "base_graph_mutated": False,
                "result_execution_success_treated_as_scientific_verification": False,
                "simulation_may_directly_verify_empirical_claim": False,
                "positive_support_grants_final_truth": False,
                "exact_inference_edge_identity_authenticated": True,
                "scientific_relation_promoted_by_producer": False,
                "transition_id_reuse_allowed": False,
                "duplicate_transition_lineage_allowed": False,
                "source_file_toctou_changes_transition_bytes": False,
                "bundle_published_atomically": True,
                "bundle_published_with_no_replace": True,
                "unsupported_publication_platforms_fail_closed": True,
                "bundle_relative_artifact_paths": True,
                "inherited_artifacts_snapshotted": True,
                "inherited_evidence_nodes_without_resolvable_artifacts_allowed": False,
                "provenance_snapshots_self_contained": True,
                "temporary_transition_staging_used": True,
                "staged_symlinks_accepted": False,
                "exclusive_staging_write_ownership_assumed": True,
                "hostile_same_os_identity_staging_tamper_resistance_claimed": False,
                "same_identity_concurrent_staging_tamper_outside_trust_boundary": True,
                "empirical_derived_without_resolvable_input_snapshots_allowed": False,
                "opaque_graph_metadata_used_as_authority": False,
                "legacy_v10_verifier_used_as_authenticated_authority": False,
                "authenticated_v11_verifier_consumed_by_legacy_critic": False,
                "verifier_identity_or_credential_authenticated": False,
                "execution_authorized_by_authentication": False,
                "positive_closeout_granted_by_authentication": False,
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        (build_root / "epistemic_graph.json").write_bytes(graph_bytes)
        (build_root / "epistemic_transition_manifest.json").write_bytes(manifest_bytes)

        target_after_written = _validate_written_bundle(
            build_root,
            graph_bytes=graph_bytes,
            manifest_bytes=manifest_bytes,
            payloads=payloads,
            program_state=program_state,
            target_node_id=target_id,
            inference_edge_id=edge_id,
        )
        if target_after_written != target_after:
            raise AuthenticatedEpistemicTransitionError(
                "written bundle target assessment differs from pre-publication assessment"
            )
        _atomic_publish_directory_no_replace(build_root, output)
        published = True
    finally:
        if not published and build_root.exists():
            shutil.rmtree(build_root, ignore_errors=True)

    return manifest


__all__ = [
    "AUTHENTICATED_TRANSITION_LINEAGE_SCHEMA_VERSION",
    "AUTHENTICATED_TRANSITION_POLICY_VERSION",
    "AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS",
    "AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE",
    "AuthenticatedEpistemicTransitionError",
    "apply_authenticated_epistemic_transition_files",
]
