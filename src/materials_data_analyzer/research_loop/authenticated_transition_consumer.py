"""Independent exact-byte consumer for one authenticated transition bundle.

The consumer re-reads the published bundle instead of trusting producer-returned booleans.
It authenticates only the current transition's provenance identity and graph realization.
It does not grant scientific authority, execution authority, calibrated confidence,
independence, verifier credentials, or positive scientific closeout.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .authenticated_inference_binding import (
    AuthenticatedInferenceBindingError,
    authenticate_inference_binding,
)
from .kernel import ResearchLoopError

AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION = "1.0"
AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION = "1.0"

_GRAPH_FILENAME = "epistemic_graph.json"
_MANIFEST_FILENAME = "epistemic_transition_manifest.json"
_AUTHENTICATED_LINEAGE_SCHEMA_VERSION = "1.0"
_AUTHENTICATED_VERIFIER_ROLE = "authenticated_domain_verification_decision"

_DIRECTIONAL_RELATIONS = {"supports", "contradicts", "falsifies"}
_RESULT_NODE_TYPES = {"analysis", "simulation", "experiment"}
_ACTION_CLASSES = {
    "existing_data_reanalysis",
    "computational_experiment",
    "sensitivity_analysis",
    "simulation",
    "replication",
    "physical_experiment",
}
_EXECUTION_MODES = {"typed_local_action", "external_result_ingest"}
_RESULT_ORIGINS = {
    "authorized_local_analysis",
    "authorized_local_simulation",
    "data_experiment",
    "external_physical_experiment",
    "external_analysis",
}
_INFERENCE_SCOPES = {
    "structural",
    "computational",
    "empirical_derived",
    "empirical_direct",
}
_TARGET_CLAIM_SCOPES = {"structural", "computational", "empirical", "mixed"}

_PROPOSAL_KEYS = {
    "schema_version",
    "transition_id",
    "base_graph_id",
    "base_graph_sha256",
    "new_graph_id",
    "target_node_id",
    "source_action",
    "result_node",
    "input_evidence_bindings",
    "proposed_inference",
    "limitations",
}
_AUTHENTICATED_LINEAGE_KEYS = {
    "schema_version",
    "transition_id",
    "base_graph_artifact",
    "proposal_artifact",
    "verification_decision_artifact",
    "result_artifact_snapshots",
    "authenticated_inference_binding",
    "scientific_authority_applied",
}
_LEGACY_LINEAGE_KEYS = {
    "transition_id",
    "parent_graph_id",
    "parent_graph_sha256",
    "proposal_sha256",
    "verification_decision_sha256",
    "result_node_id",
}
_ARTIFACT_CORE_KEYS = {"path", "sha256"}
_ARTIFACT_OPTIONAL_KEYS = {
    "source_path",
    "source_path_authoritative",
    "size_bytes",
}


class AuthenticatedTransitionConsumerError(ResearchLoopError):
    """Raised when a published authenticated-transition bundle cannot be re-authenticated."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthenticatedTransitionConsumerError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _json_object(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticatedTransitionConsumerError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AuthenticatedTransitionConsumerError(f"{field} root must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthenticatedTransitionConsumerError(f"{field} must be non-empty text")
    return value.strip()


def _strict_text(value: object, field: str) -> str:
    text = _text(value, field)
    if value != text:
        raise AuthenticatedTransitionConsumerError(
            f"{field} must not contain leading or trailing whitespace"
        )
    return text


def _sha256_text(value: object, field: str) -> str:
    text = _strict_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise AuthenticatedTransitionConsumerError(
            f"{field} must be a lowercase 64-character SHA-256"
        )
    return text


def _exact_object(
    value: object,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthenticatedTransitionConsumerError(f"{field} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing or unknown:
        raise AuthenticatedTransitionConsumerError(
            f"{field} violates its exact key contract; unknown={unknown}, missing={missing}"
        )
    return value


def _enum(value: object, allowed: set[str], field: str) -> str:
    text = _text(value, field)
    if text not in allowed:
        raise AuthenticatedTransitionConsumerError(
            f"{field} must be one of: {', '.join(sorted(allowed))}"
        )
    return text


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise AuthenticatedTransitionConsumerError(f"{field} must be a list")
    if not allow_empty and not value:
        raise AuthenticatedTransitionConsumerError(f"{field} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]")
        if text in result:
            raise AuthenticatedTransitionConsumerError(
                f"{field} must not contain duplicates"
            )
        result.append(text)
    return result


def _bundle_root(path: str | Path) -> Path:
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise AuthenticatedTransitionConsumerError(
            f"bundle root is not readable: {path}"
        ) from exc
    if not root.is_dir():
        raise AuthenticatedTransitionConsumerError(
            f"bundle root must be a directory: {root}"
        )
    return root


def _relative_bundle_parts(value: object, field: str) -> tuple[str, ...]:
    text = _strict_text(value, field)
    windows = PureWindowsPath(text)
    posix = PurePosixPath(text)
    if "\\" in text or posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise AuthenticatedTransitionConsumerError(
            f"{field} must be a portable relative bundle path"
        )
    raw_parts = text.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise AuthenticatedTransitionConsumerError(
            f"{field} must not contain empty, dot, or parent components"
        )
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    forbidden = set('<>:"\\|?*')
    for part in raw_parts:
        if any(ord(char) < 32 or char in forbidden for char in part):
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-nonportable path component"
            )
        if part.endswith((" ", ".")):
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-nonportable trailing space or dot"
            )
        basename = part.split(".", 1)[0].upper()
        if basename in reserved_names:
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains a Windows-reserved path component"
            )
    return tuple(raw_parts)


def _is_reparse_point(st: os.stat_result) -> bool:
    attributes = getattr(st, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _resolve_bundle_file(root: Path, value: object, *, field: str) -> Path:
    parts = _relative_bundle_parts(value, field)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            st = os.lstat(current)
        except OSError as exc:
            raise AuthenticatedTransitionConsumerError(
                f"{field} is not readable inside the bundle"
            ) from exc
        if stat.S_ISLNK(st.st_mode) or _is_reparse_point(st):
            raise AuthenticatedTransitionConsumerError(
                f"{field} must not traverse symlink or reparse-point components"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            raise AuthenticatedTransitionConsumerError(
                f"{field} has a non-directory parent component"
            )
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AuthenticatedTransitionConsumerError(
            f"{field} escapes the bundle root"
        ) from exc
    try:
        final_stat = os.lstat(resolved)
    except OSError as exc:
        raise AuthenticatedTransitionConsumerError(f"{field} is not readable") from exc
    if not stat.S_ISREG(final_stat.st_mode) or _is_reparse_point(final_stat):
        raise AuthenticatedTransitionConsumerError(
            f"{field} must resolve to a regular non-reparse file"
        )
    return resolved


def _read_bundle_path(root: Path, value: object, *, field: str) -> tuple[bytes, str]:
    path = _resolve_bundle_file(root, value, field=field)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AuthenticatedTransitionConsumerError(f"could not read {field}") from exc
    return raw, hashlib.sha256(raw).hexdigest()


def _artifact_binding(
    value: object,
    *,
    field: str,
    require_role: bool,
    expected_role: str | None = None,
) -> dict[str, Any]:
    required = set(_ARTIFACT_CORE_KEYS)
    allowed = set(_ARTIFACT_CORE_KEYS | _ARTIFACT_OPTIONAL_KEYS)
    if require_role:
        required.add("role")
        allowed.add("role")
    raw = _exact_object(value, required=required, allowed=allowed, field=field)
    result: dict[str, Any] = {
        "path": _strict_text(raw["path"], f"{field}.path"),
        "sha256": _sha256_text(raw["sha256"], f"{field}.sha256"),
    }
    if require_role:
        role = _text(raw["role"], f"{field}.role")
        if expected_role is not None and role != expected_role:
            raise AuthenticatedTransitionConsumerError(
                f"{field}.role must be {expected_role}"
            )
        result["role"] = role
    if "source_path" in raw:
        result["source_path"] = _text(raw["source_path"], f"{field}.source_path")
    if "source_path_authoritative" in raw:
        if raw["source_path_authoritative"] is not False:
            raise AuthenticatedTransitionConsumerError(
                f"{field}.source_path_authoritative must be false"
            )
        result["source_path_authoritative"] = False
    if "size_bytes" in raw:
        size_bytes = raw["size_bytes"]
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise AuthenticatedTransitionConsumerError(
                f"{field}.size_bytes must be a non-negative integer"
            )
        result["size_bytes"] = size_bytes
    return result


def _read_bound_artifact(
    root: Path,
    value: object,
    *,
    field: str,
    require_role: bool,
    expected_role: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    binding = _artifact_binding(
        value,
        field=field,
        require_role=require_role,
        expected_role=expected_role,
    )
    raw, actual_sha = _read_bundle_path(root, binding["path"], field=f"{field}.path")
    if actual_sha != binding["sha256"]:
        raise AuthenticatedTransitionConsumerError(
            f"{field} checksum does not match its exact bundle bytes"
        )
    if "size_bytes" in binding and binding["size_bytes"] != len(raw):
        raise AuthenticatedTransitionConsumerError(
            f"{field}.size_bytes does not match its exact bundle bytes"
        )
    return binding, raw


def _lineage_records(metadata: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw = metadata.get(key)
    if not isinstance(raw, list) or not raw:
        raise AuthenticatedTransitionConsumerError(
            f"epistemic graph metadata.{key} must be a non-empty list"
        )
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise AuthenticatedTransitionConsumerError(
                f"epistemic graph metadata.{key}[{index}] must be an object"
            )
        transition_id = _text(
            item.get("transition_id"),
            f"epistemic graph metadata.{key}[{index}].transition_id",
        )
        if transition_id in seen:
            raise AuthenticatedTransitionConsumerError(
                f"epistemic graph metadata.{key} contains duplicate transition IDs"
            )
        seen.add(transition_id)
        result.append(item)
    return result


def _proposal_result_artifacts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AuthenticatedTransitionConsumerError(
            "proposal result_node.artifact_bindings must be a non-empty list"
        )
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, item in enumerate(value):
        raw = _exact_object(
            item,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"proposal result_node.artifact_bindings[{index}]",
        )
        role = _text(raw["role"], f"proposal result_node.artifact_bindings[{index}].role")
        if role in roles:
            raise AuthenticatedTransitionConsumerError(
                "proposal result artifact roles must be unique"
            )
        roles.add(role)
        result.append(
            {
                "role": role,
                "sha256": _sha256_text(
                    raw["sha256"],
                    f"proposal result_node.artifact_bindings[{index}].sha256",
                ),
            }
        )
    return result


def _normalize_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _exact_object(
        value,
        required=set(_PROPOSAL_KEYS),
        allowed=set(_PROPOSAL_KEYS),
        field="transition proposal",
    )
    if raw["schema_version"] != "1.0":
        raise AuthenticatedTransitionConsumerError(
            "transition proposal schema_version must be 1.0"
        )
    source_action = _exact_object(
        raw["source_action"],
        required={"action_id", "action_class", "action_version", "execution_mode"},
        allowed={"action_id", "action_class", "action_version", "execution_mode"},
        field="transition proposal source_action",
    )
    action = {
        "action_id": _text(source_action["action_id"], "source_action.action_id"),
        "action_class": _enum(
            source_action["action_class"], _ACTION_CLASSES, "source_action.action_class"
        ),
        "action_version": _text(
            source_action["action_version"], "source_action.action_version"
        ),
        "execution_mode": _enum(
            source_action["execution_mode"], _EXECUTION_MODES, "source_action.execution_mode"
        ),
    }

    result_node = _exact_object(
        raw["result_node"],
        required={"node_id", "node_type", "statement", "artifact_bindings", "metadata"},
        allowed={"node_id", "node_type", "statement", "artifact_bindings", "metadata"},
        field="transition proposal result_node",
    )
    result_metadata = _exact_object(
        result_node["metadata"],
        required={"result_origin"},
        allowed={"result_origin", "claim_scope", "notes"},
        field="transition proposal result_node.metadata",
    )
    normalized_metadata = dict(result_metadata)
    normalized_metadata["result_origin"] = _enum(
        result_metadata["result_origin"],
        _RESULT_ORIGINS,
        "transition proposal result_node.metadata.result_origin",
    )
    # Producer validation preserves optional claim_scope/notes values verbatim.
    # They are opaque result metadata here and must not be upgraded into provenance.
    result_origin = str(normalized_metadata["result_origin"])
    result_node_type = _enum(
        result_node["node_type"],
        _RESULT_NODE_TYPES,
        "transition proposal result_node.node_type",
    )
    execution_mode = str(action["execution_mode"])
    if execution_mode == "typed_local_action" and result_origin in {
        "external_physical_experiment",
        "external_analysis",
    }:
        raise AuthenticatedTransitionConsumerError(
            "external physical/analysis results require execution_mode=external_result_ingest"
        )
    if execution_mode == "external_result_ingest" and result_origin in {
        "authorized_local_analysis",
        "authorized_local_simulation",
    }:
        raise AuthenticatedTransitionConsumerError(
            "authorized local results require execution_mode=typed_local_action"
        )
    if result_node_type == "simulation" and result_origin != "authorized_local_simulation":
        raise AuthenticatedTransitionConsumerError(
            "simulation nodes require authorized_local_simulation origin"
        )
    if result_node_type == "analysis" and result_origin not in {
        "authorized_local_analysis",
        "external_analysis",
    }:
        raise AuthenticatedTransitionConsumerError(
            "analysis nodes require an analysis result origin"
        )

    input_evidence = raw["input_evidence_bindings"]
    if not isinstance(input_evidence, list):
        raise AuthenticatedTransitionConsumerError(
            "transition proposal input_evidence_bindings must be a list"
        )
    if input_evidence:
        raise AuthenticatedTransitionConsumerError(
            "current authenticated producer contract does not support unresolved input evidence"
        )

    proposed = _exact_object(
        raw["proposed_inference"],
        required={"tests_edge_id", "inference_edge_id", "relation", "rationale"},
        allowed={"tests_edge_id", "inference_edge_id", "relation", "rationale"},
        field="transition proposal proposed_inference",
    )
    tests_edge_id = _text(
        proposed["tests_edge_id"], "transition proposal proposed_inference.tests_edge_id"
    )
    inference_edge_id = _text(
        proposed["inference_edge_id"],
        "transition proposal proposed_inference.inference_edge_id",
    )
    if tests_edge_id == inference_edge_id:
        raise AuthenticatedTransitionConsumerError(
            "proposal tests and directional inference edge IDs must differ"
        )

    base_graph_id = _text(raw["base_graph_id"], "transition proposal base_graph_id")
    new_graph_id = _text(raw["new_graph_id"], "transition proposal new_graph_id")
    if base_graph_id == new_graph_id:
        raise AuthenticatedTransitionConsumerError(
            "transition proposal new_graph_id must differ from base_graph_id"
        )
    return {
        "schema_version": "1.0",
        "transition_id": _text(raw["transition_id"], "transition proposal transition_id"),
        "base_graph_id": base_graph_id,
        "base_graph_sha256": _sha256_text(
            raw["base_graph_sha256"], "transition proposal base_graph_sha256"
        ),
        "new_graph_id": new_graph_id,
        "target_node_id": _text(
            raw["target_node_id"], "transition proposal target_node_id"
        ),
        "source_action": action,
        "result_node": {
            "node_id": _text(result_node["node_id"], "transition proposal result_node.node_id"),
            "node_type": result_node_type,
            "statement": _text(
                result_node["statement"], "transition proposal result_node.statement"
            ),
            "artifact_bindings": _proposal_result_artifacts(
                result_node["artifact_bindings"]
            ),
            "metadata": normalized_metadata,
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": tests_edge_id,
            "inference_edge_id": inference_edge_id,
            "relation": _enum(
                proposed["relation"],
                _DIRECTIONAL_RELATIONS,
                "transition proposal proposed_inference.relation",
            ),
            "rationale": _text(
                proposed["rationale"],
                "transition proposal proposed_inference.rationale",
            ),
        },
        "limitations": _string_list(raw["limitations"], "transition proposal limitations"),
    }


def _normalized_graph_ids(value: object, *, id_field: str, field: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise AuthenticatedTransitionConsumerError(f"{field} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise AuthenticatedTransitionConsumerError(f"{field}[{index}] must be an object")
        identifier = _text(item.get(id_field), f"{field}[{index}].{id_field}")
        if identifier in result:
            raise AuthenticatedTransitionConsumerError(
                f"{field} contains duplicate normalized {id_field} values"
            )
        result[identifier] = item
    return result


def _target_claim_scope(base_graph: Mapping[str, Any], target_node_id: str) -> str | None:
    nodes = _normalized_graph_ids(
        base_graph.get("nodes"), id_field="node_id", field="base graph nodes"
    )
    target = nodes.get(target_node_id)
    if target is None:
        raise AuthenticatedTransitionConsumerError(
            "transition target node is absent from the exact base graph"
        )
    node_type = _enum(
        target.get("node_type"),
        {"hypothesis", "claim", "conclusion"},
        "base graph target node_type",
    )
    del node_type
    metadata = target.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    scope = metadata.get("claim_scope")
    if scope is None:
        return None
    return _enum(scope, _TARGET_CLAIM_SCOPES, "base graph target claim_scope")


def _validate_inference_scope(
    *,
    proposal: Mapping[str, Any],
    inference_scope: str,
    target_claim_scope: str | None,
) -> None:
    if inference_scope in {"empirical_derived", "empirical_direct"}:
        raise AuthenticatedTransitionConsumerError(
            "empirical inference remains fail-closed until checksum-bound resolvable evidence-origin provenance is authenticated"
        )
    if inference_scope not in _INFERENCE_SCOPES:
        raise AuthenticatedTransitionConsumerError("authenticated inference_scope is unsupported")
    if target_claim_scope is None:
        raise AuthenticatedTransitionConsumerError(
            "authenticated inference requires target metadata.claim_scope"
        )
    result = proposal["result_node"]
    result_node_type = str(result["node_type"])
    metadata = result["metadata"]
    if not isinstance(metadata, Mapping):
        raise AuthenticatedTransitionConsumerError("normalized result metadata is malformed")
    result_origin = str(metadata["result_origin"])
    if result_node_type == "simulation" and inference_scope not in {
        "structural",
        "computational",
    }:
        raise AuthenticatedTransitionConsumerError(
            "simulation result cannot authenticate empirical inference scope"
        )
    if result_node_type == "analysis" and inference_scope in {
        "empirical_derived",
        "empirical_direct",
    }:
        raise AuthenticatedTransitionConsumerError(
            "current bundle consumer keeps analysis empirical scope fail-closed until evidence-origin support exists"
        )
    if result_node_type == "experiment":
        if result_origin == "external_physical_experiment":
            if inference_scope != "empirical_direct":
                raise AuthenticatedTransitionConsumerError(
                    "external physical experiment requires empirical_direct scope"
                )
        elif result_origin == "data_experiment":
            raise AuthenticatedTransitionConsumerError(
                "data experiment remains fail-closed until evidence-origin support exists"
            )
        else:
            raise AuthenticatedTransitionConsumerError(
                "experiment result origin is incompatible with authenticated scope"
            )
    compatible = {
        "structural": {"structural", "mixed"},
        "computational": {"computational", "mixed"},
        "empirical_derived": {"empirical", "mixed"},
        "empirical_direct": {"empirical", "mixed"},
    }[inference_scope]
    if target_claim_scope not in compatible:
        raise AuthenticatedTransitionConsumerError(
            "authenticated inference scope is incompatible with target claim_scope"
        )


def _result_snapshot_bindings(
    root: Path, value: object
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    if not isinstance(value, list) or not value:
        raise AuthenticatedTransitionConsumerError(
            "current authenticated lineage result_artifact_snapshots must be non-empty"
        )
    bindings: list[dict[str, Any]] = []
    bytes_by_role: dict[str, bytes] = {}
    for index, item in enumerate(value):
        binding, raw = _read_bound_artifact(
            root,
            item,
            field=f"current authenticated lineage result_artifact_snapshots[{index}]",
            require_role=True,
        )
        role = str(binding["role"])
        if role in bytes_by_role:
            raise AuthenticatedTransitionConsumerError(
                "current authenticated lineage result artifact roles must be unique"
            )
        bindings.append(binding)
        bytes_by_role[role] = raw
    return bindings, bytes_by_role


def _graph_result_binding_identity(value: object, *, field: str) -> dict[str, dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AuthenticatedTransitionConsumerError(f"{field} must be a non-empty list")
    result: dict[str, dict[str, str]] = {}
    for index, item in enumerate(value):
        raw = _exact_object(
            item,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"{field}[{index}]",
        )
        role = _text(raw["role"], f"{field}[{index}].role")
        if role in result:
            raise AuthenticatedTransitionConsumerError(f"{field} roles must be unique")
        result[role] = {
            "role": role,
            "path": _strict_text(raw["path"], f"{field}[{index}].path"),
            "sha256": _sha256_text(raw["sha256"], f"{field}[{index}].sha256"),
        }
    return result




def _artifact_role_sha_identity(value: object, *, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise AuthenticatedTransitionConsumerError(f"{field} must be a list")
    result: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, item in enumerate(value):
        raw = _exact_object(
            item,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"{field}[{index}]",
        )
        role = _text(raw["role"], f"{field}[{index}].role")
        if role in roles:
            raise AuthenticatedTransitionConsumerError(f"{field} roles must be unique")
        roles.add(role)
        result.append(
            {
                "role": role,
                "sha256": _sha256_text(raw["sha256"], f"{field}[{index}].sha256"),
            }
        )
    return result


def _node_append_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = dict(value)
    if "artifact_bindings" in result:
        result["artifact_bindings"] = _artifact_role_sha_identity(
            result["artifact_bindings"], field=f"{field}.artifact_bindings"
        )
    return result


def _edge_append_identity(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    result = dict(value)
    verifier = result.get("verification_artifact")
    if verifier is not None:
        raw = _exact_object(
            verifier,
            required={"role", "path", "sha256"},
            allowed={"role", "path", "sha256"},
            field=f"{field}.verification_artifact",
        )
        result["verification_artifact"] = {
            "role": _text(raw["role"], f"{field}.verification_artifact.role"),
            "sha256": _sha256_text(
                raw["sha256"], f"{field}.verification_artifact.sha256"
            ),
        }
    return result


def _lineage_artifact_identity(
    value: object, *, field: str, require_role: bool
) -> dict[str, str]:
    binding = _artifact_binding(
        value,
        field=field,
        require_role=require_role,
        expected_role=_AUTHENTICATED_VERIFIER_ROLE if require_role and "verification" in field else None,
    )
    result = {"sha256": str(binding["sha256"])}
    if require_role:
        result["role"] = str(binding["role"])
    return result


def _authenticated_lineage_append_identity(
    value: object, *, field: str
) -> dict[str, Any]:
    raw = _exact_object(
        value,
        required=set(_AUTHENTICATED_LINEAGE_KEYS),
        allowed=set(_AUTHENTICATED_LINEAGE_KEYS),
        field=field,
    )
    snapshots = raw["result_artifact_snapshots"]
    if not isinstance(snapshots, list):
        raise AuthenticatedTransitionConsumerError(
            f"{field}.result_artifact_snapshots must be a list"
        )
    return {
        "schema_version": raw["schema_version"],
        "transition_id": _text(raw["transition_id"], f"{field}.transition_id"),
        "base_graph_artifact": _lineage_artifact_identity(
            raw["base_graph_artifact"], field=f"{field}.base_graph_artifact", require_role=False
        ),
        "proposal_artifact": _lineage_artifact_identity(
            raw["proposal_artifact"], field=f"{field}.proposal_artifact", require_role=False
        ),
        "verification_decision_artifact": _lineage_artifact_identity(
            raw["verification_decision_artifact"],
            field=f"{field}.verification_decision_artifact",
            require_role=True,
        ),
        "result_artifact_snapshots": [
            _lineage_artifact_identity(
                item,
                field=f"{field}.result_artifact_snapshots[{index}]",
                require_role=True,
            )
            for index, item in enumerate(snapshots)
        ],
        "authenticated_inference_binding": dict(raw["authenticated_inference_binding"])
        if isinstance(raw["authenticated_inference_binding"], Mapping)
        else raw["authenticated_inference_binding"],
        "scientific_authority_applied": raw["scientific_authority_applied"],
    }


def _metadata_list(value: Mapping[str, Any], key: str, *, field: str) -> list[Any]:
    raw = value.get(key, [])
    if not isinstance(raw, list):
        raise AuthenticatedTransitionConsumerError(f"{field}.{key} must be a list")
    return raw


def _verify_successor_is_exact_append(
    *,
    base_graph: Mapping[str, Any],
    successor_graph: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> None:
    base_nodes = _normalized_graph_ids(
        base_graph.get("nodes"), id_field="node_id", field="base graph nodes"
    )
    base_edges = _normalized_graph_ids(
        base_graph.get("edges"), id_field="edge_id", field="base graph edges"
    )
    successor_nodes = _normalized_graph_ids(
        successor_graph.get("nodes"), id_field="node_id", field="epistemic graph nodes"
    )
    successor_edges = _normalized_graph_ids(
        successor_graph.get("edges"), id_field="edge_id", field="epistemic graph edges"
    )
    result_id = str(proposal["result_node"]["node_id"])
    tests_edge_id = str(proposal["proposed_inference"]["tests_edge_id"])
    inference_edge_id = str(proposal["proposed_inference"]["inference_edge_id"])
    if result_id in base_nodes or tests_edge_id in base_edges or inference_edge_id in base_edges:
        raise AuthenticatedTransitionConsumerError(
            "authenticated transition IDs must be absent from the exact bound base graph"
        )
    if set(successor_nodes) != set(base_nodes) | {result_id}:
        raise AuthenticatedTransitionConsumerError(
            "successor node set is not the exact bound base plus one authenticated result node"
        )
    if set(successor_edges) != set(base_edges) | {tests_edge_id, inference_edge_id}:
        raise AuthenticatedTransitionConsumerError(
            "successor edge set is not the exact bound base plus the authenticated tests/directional edges"
        )
    for node_id, base_node in base_nodes.items():
        if _node_append_identity(
            base_node, field=f"base graph node {node_id}"
        ) != _node_append_identity(
            successor_nodes[node_id], field=f"successor inherited node {node_id}"
        ):
            raise AuthenticatedTransitionConsumerError(
                f"successor inherited node {node_id} diverges from the exact bound base"
            )
    for edge_id, base_edge in base_edges.items():
        if _edge_append_identity(
            base_edge, field=f"base graph edge {edge_id}"
        ) != _edge_append_identity(
            successor_edges[edge_id], field=f"successor inherited edge {edge_id}"
        ):
            raise AuthenticatedTransitionConsumerError(
                f"successor inherited edge {edge_id} diverges from the exact bound base"
            )

    base_metadata = base_graph.get("metadata")
    successor_metadata = successor_graph.get("metadata")
    if base_metadata is None:
        base_metadata = {}
    if not isinstance(base_metadata, Mapping) or not isinstance(successor_metadata, Mapping):
        raise AuthenticatedTransitionConsumerError(
            "base/successor graph metadata must be objects for append-only verification"
        )
    lineage_keys = {"transition_lineage", "authenticated_transition_lineage"}
    base_other = {key: value for key, value in base_metadata.items() if key not in lineage_keys}
    successor_other = {
        key: value for key, value in successor_metadata.items() if key not in lineage_keys
    }
    if base_other != successor_other:
        raise AuthenticatedTransitionConsumerError(
            "successor graph rewrites non-lineage metadata from the exact bound base"
        )
    base_legacy = _metadata_list(base_metadata, "transition_lineage", field="base metadata")
    successor_legacy = _metadata_list(
        successor_metadata, "transition_lineage", field="successor metadata"
    )
    if len(successor_legacy) != len(base_legacy) + 1 or successor_legacy[:-1] != base_legacy:
        raise AuthenticatedTransitionConsumerError(
            "successor legacy transition lineage is not an exact one-record append"
        )
    base_authenticated = _metadata_list(
        base_metadata, "authenticated_transition_lineage", field="base metadata"
    )
    successor_authenticated = _metadata_list(
        successor_metadata, "authenticated_transition_lineage", field="successor metadata"
    )
    if len(successor_authenticated) != len(base_authenticated) + 1:
        raise AuthenticatedTransitionConsumerError(
            "successor authenticated lineage is not an exact one-record append"
        )
    for index, base_record in enumerate(base_authenticated):
        if _authenticated_lineage_append_identity(
            base_record, field=f"base authenticated lineage[{index}]"
        ) != _authenticated_lineage_append_identity(
            successor_authenticated[index], field=f"successor authenticated lineage[{index}]"
        ):
            raise AuthenticatedTransitionConsumerError(
                "successor rewrites inherited authenticated-lineage identity"
            )
def _verify_graph_realization(
    graph: Mapping[str, Any],
    *,
    proposal: Mapping[str, Any],
    binding: Mapping[str, Any],
    result_snapshots: list[Mapping[str, Any]],
) -> None:
    graph_id = _text(graph.get("graph_id"), "epistemic graph graph_id")
    if graph_id != proposal["new_graph_id"]:
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph graph_id does not match proposal new_graph_id"
        )
    nodes = _normalized_graph_ids(
        graph.get("nodes"), id_field="node_id", field="epistemic graph nodes"
    )
    edges = _normalized_graph_ids(
        graph.get("edges"), id_field="edge_id", field="epistemic graph edges"
    )
    result_id = str(binding["result_node_id"])
    result_node = nodes.get(result_id)
    if result_node is None:
        raise AuthenticatedTransitionConsumerError(
            "authenticated result node is absent from the epistemic graph"
        )
    proposal_result = proposal["result_node"]
    snapshot_by_role = {
        str(item["role"]): {
            "role": str(item["role"]),
            "path": str(item["path"]),
            "sha256": str(item["sha256"]),
        }
        for item in result_snapshots
    }
    proposal_by_role = {
        str(item["role"]): str(item["sha256"])
        for item in proposal_result["artifact_bindings"]
    }
    if set(snapshot_by_role) != set(proposal_by_role):
        raise AuthenticatedTransitionConsumerError(
            "published result snapshot roles do not match exact proposal result roles"
        )
    for role, expected_sha in proposal_by_role.items():
        if snapshot_by_role[role]["sha256"] != expected_sha:
            raise AuthenticatedTransitionConsumerError(
                "published result snapshot checksum does not match exact proposal"
            )
    graph_artifacts = _graph_result_binding_identity(
        result_node.get("artifact_bindings"), field="epistemic graph result artifact_bindings"
    )
    if graph_artifacts != snapshot_by_role:
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph result artifact bindings do not match exact bundle snapshots"
        )

    expected_metadata = dict(proposal_result["metadata"])
    expected_metadata["source_action"] = dict(proposal["source_action"])
    expected_metadata["input_evidence_bindings"] = []
    expected_metadata["transition_id"] = proposal["transition_id"]
    expected_metadata["limitations"] = list(proposal["limitations"])
    expected_result_node = {
        "node_id": result_id,
        "node_type": proposal_result["node_type"],
        "statement": proposal_result["statement"],
        "execution_status": "completed",
        "artifact_bindings": list(snapshot_by_role.values()),
        "metadata": expected_metadata,
    }
    if dict(result_node) != expected_result_node:
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph result node does not match normalized exact proposal semantics"
        )

    proposed = proposal["proposed_inference"]
    tests_edge_id = str(proposed["tests_edge_id"])
    tests_edge = edges.get(tests_edge_id)
    expected_tests = {
        "edge_id": tests_edge_id,
        "source_node_id": result_id,
        "target_node_id": proposal["target_node_id"],
        "relation": "tests",
        "assessment_level": "proposal",
        "rationale": (
            "The completed result was introduced to test this target; execution success alone "
            "does not establish scientific support, contradiction, or falsification."
        ),
        "active": True,
    }
    if tests_edge is None or dict(tests_edge) != expected_tests:
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph tests edge does not match authenticated transition semantics"
        )

    inference_edge_id = str(binding["inference_edge_id"])
    inference_edge = edges.get(inference_edge_id)
    expected_inference = {
        "edge_id": inference_edge_id,
        "source_node_id": result_id,
        "target_node_id": proposal["target_node_id"],
        "relation": binding["relation"],
        "assessment_level": "diagnostic",
        "rationale": proposed["rationale"],
        "active": True,
    }
    if inference_edge is None or dict(inference_edge) != expected_inference:
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph directional edge is not the diagnostic exact authenticated edge"
        )


def _binding_core(value: Mapping[str, Any], *, require_role: bool) -> dict[str, str]:
    result = {"path": str(value["path"]), "sha256": str(value["sha256"])}
    if require_role:
        result["role"] = str(value["role"])
    return result


def _verify_manifest(
    manifest: Mapping[str, Any],
    *,
    graph_sha256: str,
    graph_id: str,
    transition_id: str,
    base_binding: Mapping[str, Any],
    proposal_binding: Mapping[str, Any],
    verifier_binding: Mapping[str, Any],
    result_bindings: list[Mapping[str, Any]],
    authenticated_binding: Mapping[str, Any],
) -> None:
    if manifest.get("transition_id") != transition_id:
        raise AuthenticatedTransitionConsumerError(
            "manifest transition_id does not match current authenticated lineage"
        )
    successor = manifest.get("successor_graph")
    if not isinstance(successor, Mapping):
        raise AuthenticatedTransitionConsumerError("manifest successor_graph must be an object")
    if (
        successor.get("graph_id") != graph_id
        or successor.get("path") != _GRAPH_FILENAME
        or successor.get("sha256") != graph_sha256
    ):
        raise AuthenticatedTransitionConsumerError(
            "manifest successor_graph does not match exact epistemic graph bytes"
        )

    checks = (
        ("base_graph_binding", base_binding, False),
        ("proposal_binding", proposal_binding, False),
        ("verification_decision_binding", verifier_binding, True),
    )
    for name, expected, require_role in checks:
        raw = manifest.get(name)
        normalized = _artifact_binding(
            raw,
            field=f"manifest {name}",
            require_role=require_role,
            expected_role=_AUTHENTICATED_VERIFIER_ROLE if require_role else None,
        )
        if normalized != dict(expected):
            raise AuthenticatedTransitionConsumerError(
                f"manifest {name} does not match current authenticated lineage"
            )

    manifest_provenance = manifest.get("result_artifact_provenance")
    if not isinstance(manifest_provenance, list):
        raise AuthenticatedTransitionConsumerError(
            "manifest result_artifact_provenance must be a list"
        )
    normalized_provenance = [
        _artifact_binding(
            item,
            field=f"manifest result_artifact_provenance[{index}]",
            require_role=True,
        )
        for index, item in enumerate(manifest_provenance)
    ]
    if normalized_provenance != [dict(item) for item in result_bindings]:
        raise AuthenticatedTransitionConsumerError(
            "manifest result_artifact_provenance does not match current lineage snapshots"
        )

    manifest_graph_bindings = _graph_result_binding_identity(
        manifest.get("result_artifact_bindings"),
        field="manifest result_artifact_bindings",
    )
    expected_graph_bindings = {
        str(item["role"]): _binding_core(item, require_role=True)
        for item in result_bindings
    }
    if manifest_graph_bindings != expected_graph_bindings:
        raise AuthenticatedTransitionConsumerError(
            "manifest result_artifact_bindings do not match exact result snapshots"
        )
    if manifest.get("authenticated_inference_binding") != dict(authenticated_binding):
        raise AuthenticatedTransitionConsumerError(
            "manifest authenticated_inference_binding does not match recomputed exact binding"
        )
    if manifest.get("inference_assessment_level") != "diagnostic":
        raise AuthenticatedTransitionConsumerError(
            "manifest must describe the producer inference as diagnostic-only"
        )


def authenticate_transition_bundle(bundle_root: str | Path) -> dict[str, Any]:
    """Re-authenticate the current transition in a published producer bundle.

    The returned report is provenance-only. It deliberately does not authenticate the
    verifier's institutional identity or promote the diagnostic graph edge to scientific
    authority. The entire historical authenticated-lineage chain is also outside this
    consumer's claim; only the final/current transition is independently rechecked here.
    """
    root = _bundle_root(bundle_root)
    graph_raw, graph_sha = _read_bundle_path(root, _GRAPH_FILENAME, field="epistemic graph")
    manifest_raw, manifest_sha = _read_bundle_path(
        root, _MANIFEST_FILENAME, field="epistemic transition manifest"
    )
    graph = _json_object(graph_raw, field="epistemic graph")
    manifest = _json_object(manifest_raw, field="epistemic transition manifest")

    metadata = graph.get("metadata")
    if not isinstance(metadata, Mapping):
        raise AuthenticatedTransitionConsumerError(
            "epistemic graph metadata must be an object"
        )
    authenticated_records = _lineage_records(metadata, "authenticated_transition_lineage")
    legacy_records = _lineage_records(metadata, "transition_lineage")
    current = _exact_object(
        authenticated_records[-1],
        required=set(_AUTHENTICATED_LINEAGE_KEYS),
        allowed=set(_AUTHENTICATED_LINEAGE_KEYS),
        field="current authenticated lineage",
    )
    if current["schema_version"] != _AUTHENTICATED_LINEAGE_SCHEMA_VERSION:
        raise AuthenticatedTransitionConsumerError(
            "current authenticated lineage schema_version is unsupported"
        )
    if current.get("scientific_authority_applied") is not False:
        raise AuthenticatedTransitionConsumerError(
            "producer lineage must remain diagnostic-only and set scientific_authority_applied=false"
        )
    current_legacy = _exact_object(
        legacy_records[-1],
        required=set(_LEGACY_LINEAGE_KEYS),
        allowed=set(_LEGACY_LINEAGE_KEYS),
        field="current legacy transition lineage",
    )
    transition_id = _text(current["transition_id"], "current authenticated transition_id")
    if _text(current_legacy["transition_id"], "current legacy transition_id") != transition_id:
        raise AuthenticatedTransitionConsumerError(
            "current authenticated and legacy lineage transition IDs diverge"
        )

    base_binding, base_raw = _read_bound_artifact(
        root,
        current["base_graph_artifact"],
        field="current authenticated lineage base_graph_artifact",
        require_role=False,
    )
    proposal_binding, proposal_raw = _read_bound_artifact(
        root,
        current["proposal_artifact"],
        field="current authenticated lineage proposal_artifact",
        require_role=False,
    )
    verifier_binding, verifier_raw = _read_bound_artifact(
        root,
        current["verification_decision_artifact"],
        field="current authenticated lineage verification_decision_artifact",
        require_role=True,
        expected_role=_AUTHENTICATED_VERIFIER_ROLE,
    )
    result_bindings, _result_bytes = _result_snapshot_bindings(
        root, current["result_artifact_snapshots"]
    )

    base_graph = _json_object(base_raw, field="current exact base graph snapshot")
    proposal_raw_object = _json_object(proposal_raw, field="current exact transition proposal")
    proposal = _normalize_proposal(proposal_raw_object)
    base_graph_id = _text(base_graph.get("graph_id"), "current exact base graph graph_id")
    if base_graph_id != proposal["base_graph_id"]:
        raise AuthenticatedTransitionConsumerError(
            "exact base graph graph_id does not match proposal base_graph_id"
        )
    if base_binding["sha256"] != proposal["base_graph_sha256"]:
        raise AuthenticatedTransitionConsumerError(
            "exact base graph checksum does not match proposal base_graph_sha256"
        )

    try:
        recomputed = authenticate_inference_binding(
            proposal_bytes=proposal_raw,
            verification_decision_bytes=verifier_raw,
            expected_base_graph_sha256=base_binding["sha256"],
        )
    except AuthenticatedInferenceBindingError as exc:
        raise AuthenticatedTransitionConsumerError(
            "current exact inference binding could not be independently re-authenticated"
        ) from exc
    stored_binding = current.get("authenticated_inference_binding")
    if not isinstance(stored_binding, Mapping) or dict(stored_binding) != recomputed:
        raise AuthenticatedTransitionConsumerError(
            "stored current inference binding does not equal independent recomputation"
        )
    if recomputed["transition_id"] != transition_id:
        raise AuthenticatedTransitionConsumerError(
            "recomputed binding transition_id diverges from current lineage"
        )

    expected_legacy = {
        "transition_id": transition_id,
        "parent_graph_id": base_graph_id,
        "parent_graph_sha256": str(base_binding["sha256"]),
        "proposal_sha256": str(proposal_binding["sha256"]),
        "verification_decision_sha256": str(verifier_binding["sha256"]),
        "result_node_id": str(recomputed["result_node_id"]),
    }
    normalized_legacy = {
        key: (
            _sha256_text(current_legacy[key], f"current legacy {key}")
            if key.endswith("sha256")
            else _text(current_legacy[key], f"current legacy {key}")
        )
        for key in _LEGACY_LINEAGE_KEYS
    }
    if normalized_legacy != expected_legacy:
        raise AuthenticatedTransitionConsumerError(
            "current legacy lineage does not identify the same exact transition"
        )

    target_scope = _target_claim_scope(base_graph, str(proposal["target_node_id"]))
    _validate_inference_scope(
        proposal=proposal,
        inference_scope=str(recomputed["inference_scope"]),
        target_claim_scope=target_scope,
    )
    _verify_successor_is_exact_append(
        base_graph=base_graph,
        successor_graph=graph,
        proposal=proposal,
    )
    _verify_graph_realization(
        graph,
        proposal=proposal,
        binding=recomputed,
        result_snapshots=result_bindings,
    )
    graph_id = _text(graph.get("graph_id"), "epistemic graph graph_id")
    _verify_manifest(
        manifest,
        graph_sha256=graph_sha,
        graph_id=graph_id,
        transition_id=transition_id,
        base_binding=base_binding,
        proposal_binding=proposal_binding,
        verifier_binding=verifier_binding,
        result_bindings=result_bindings,
        authenticated_binding=recomputed,
    )

    return {
        "schema_version": AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION,
        "consumer_policy_version": AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION,
        "bundle_root": str(root),
        "current_transition_exact_provenance_authenticated": True,
        "transition_id": transition_id,
        "inference_edge_id": recomputed["inference_edge_id"],
        "result_node_id": recomputed["result_node_id"],
        "target_node_id": recomputed["target_node_id"],
        "relation": recomputed["relation"],
        "inference_scope": recomputed["inference_scope"],
        "graph_binding": {"path": _GRAPH_FILENAME, "sha256": graph_sha},
        "manifest_binding": {"path": _MANIFEST_FILENAME, "sha256": manifest_sha},
        "base_graph_binding": _binding_core(base_binding, require_role=False),
        "proposal_binding": _binding_core(proposal_binding, require_role=False),
        "verification_decision_binding": _binding_core(
            verifier_binding, require_role=True
        ),
        "result_artifact_bindings": [
            _binding_core(item, require_role=True) for item in result_bindings
        ],
        "authenticated_inference_binding": dict(recomputed),
        "authority_boundary": {
            "scientific_authority_applied": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "positive_closeout_granted": False,
            "verifier_identity_or_credential_authenticated": False,
            "support_independence_established": False,
            "empirical_origin_independently_established": False,
            "historical_authenticated_lineage_chain_reauthenticated": False,
            "manifest_authority_flags_used_as_authentication_evidence": False,
            "bundle_tree_stability_after_return_asserted": False,
            "hostile_concurrent_bundle_mutation_resistance_claimed": False,
        },
    }


__all__ = [
    "AUTHENTICATED_TRANSITION_CONSUMER_POLICY_VERSION",
    "AUTHENTICATED_TRANSITION_CONSUMER_SCHEMA_VERSION",
    "AuthenticatedTransitionConsumerError",
    "authenticate_transition_bundle",
]
