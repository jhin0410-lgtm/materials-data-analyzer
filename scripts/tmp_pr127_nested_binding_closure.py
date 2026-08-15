from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
TESTS = Path("tests/test_authenticated_epistemic_transition_nested_binding_contract.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    anchor = '''_AUTHENTICATED_TRANSITION_LINEAGE_KEYS = frozenset(
    {
        "schema_version",
        "transition_id",
        "base_graph_artifact",
        "proposal_artifact",
        "verification_decision_artifact",
        "result_artifact_snapshots",
        "authenticated_inference_binding",
        "scientific_authority_applied",
    }
)
'''
    replacement = anchor + '''_LINEAGE_ARTIFACT_REQUIRED_KEYS = frozenset({"path", "sha256"})
_LINEAGE_ARTIFACT_OPTIONAL_KEYS = frozenset(
    {"source_path", "source_path_authoritative", "size_bytes"}
)
_LINEAGE_ARTIFACT_ALLOWED_KEYS = (
    _LINEAGE_ARTIFACT_REQUIRED_KEYS | _LINEAGE_ARTIFACT_OPTIONAL_KEYS
)
_LINEAGE_ROLE_ARTIFACT_ALLOWED_KEYS = _LINEAGE_ARTIFACT_ALLOWED_KEYS | {"role"}
'''
    text = replace_once(text, anchor, replacement, label="artifact-key-constants")

    marker = '\ndef _snapshot_lineage_binding(\n'
    if text.count(marker) != 1:
        raise SystemExit(f"sanitizer insertion anchor count={text.count(marker)}")
    helper = r'''

def _validated_lineage_artifact_fields(
    raw: Mapping[str, Any], *, field: str, require_role: bool
) -> dict[str, Any]:
    required = set(_LINEAGE_ARTIFACT_REQUIRED_KEYS)
    allowed = set(_LINEAGE_ARTIFACT_ALLOWED_KEYS)
    if require_role:
        required.add("role")
        allowed = set(_LINEAGE_ROLE_ARTIFACT_ALLOWED_KEYS)
    raw_keys = set(raw)
    unknown = sorted(raw_keys - allowed)
    missing = sorted(required - raw_keys)
    if unknown or missing:
        raise AuthenticatedEpistemicTransitionError(
            f"{field} violates the inherited artifact key contract; "
            f"unknown={unknown}, missing={missing}"
        )

    result: dict[str, Any] = {
        "path": _lineage_identity(raw, "path"),
        "sha256": _lineage_sha256(raw, "sha256"),
    }
    if require_role:
        result["role"] = _lineage_identity(raw, "role")

    if "source_path" in raw:
        result["source_path"] = _lineage_identity(raw, "source_path")
    if "source_path_authoritative" in raw:
        if raw.get("source_path_authoritative") is not False:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.source_path_authoritative must be false when present"
            )
        result["source_path_authoritative"] = False
    if "size_bytes" in raw:
        size_bytes = raw.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise AuthenticatedEpistemicTransitionError(
                f"{field}.size_bytes must be a non-negative integer when present"
            )
        result["size_bytes"] = size_bytes
    return result
'''
    text = text.replace(marker, helper + marker, 1)

    old = '''    copied = dict(raw)
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
'''
    new = '''    validated = _validated_lineage_artifact_fields(
        raw, field=field, require_role="role" in raw
    )
    copied: dict[str, Any] = {
        "path": bundle_path,
        "source_path": str(source),
        "source_path_authoritative": False,
        "sha256": actual_sha,
        "size_bytes": len(data),
    }
    if "role" in validated:
        copied["role"] = validated["role"]
    return copied
'''
    text = replace_once(text, old, new, label="snapshot-lineage reconstruction")

    old = '''def _captured_lineage_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
) -> tuple[dict[str, Any], bytes]:
'''
    new = '''def _captured_lineage_binding(
    raw: Mapping[str, Any],
    *,
    artifact_root: Path,
    bundle_path: str,
    field: str,
    payloads: dict[str, bytes],
    require_role: bool,
) -> tuple[dict[str, Any], bytes]:
'''
    text = replace_once(text, old, new, label="captured-lineage signature")

    old = '''    copied = dict(raw)
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
'''
    new = '''    validated = _validated_lineage_artifact_fields(
        raw, field=field, require_role=require_role
    )
    copied: dict[str, Any] = {
        "path": bundle_path,
        "source_path": str(source),
        "source_path_authoritative": False,
        "sha256": actual_sha,
        "size_bytes": len(data),
    }
    if require_role:
        copied["role"] = validated["role"]
    return copied, data
'''
    text = replace_once(text, old, new, label="captured-lineage reconstruction")

    old = '''            captured[name] = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.{name}",
                payloads=payloads,
            )
'''
    new = '''            captured[name] = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.{name}",
                payloads=payloads,
                require_role=name == "verification_decision_artifact",
            )
'''
    text = replace_once(text, old, new, label="captured-lineage artifact context")

    old = '''            copied, _data = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.result_artifact_snapshots[{result_index}]",
                payloads=payloads,
            )
'''
    new = '''            copied, _data = _captured_lineage_binding(
                raw_binding,
                artifact_root=artifact_root,
                bundle_path=relative,
                field=f"{field}.result_artifact_snapshots[{result_index}]",
                payloads=payloads,
                require_role=True,
            )
'''
    text = replace_once(text, old, new, label="captured-lineage result context")

    old = '''def _lineage_artifact_metadata_identity(
    value: object, *, field: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthenticatedEpistemicTransitionError(f"{field} must be an object")
    result: dict[str, Any] = {"sha256": _lineage_sha256(value, "sha256")}
    if "role" in value:
        result["role"] = _lineage_identity(value, "role")
    # Paths, source-path annotations, and size are rebundling metadata rather than
    # graph-hop identity. Validate them when present, but compare authority identity
    # only by exact checksum and role so a portable re-snapshot remains equivalent.
    authoritative = value.get("source_path_authoritative")
    if authoritative is not None and authoritative is not False:
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.source_path_authoritative must remain false"
        )
    size_bytes = value.get("size_bytes")
    if size_bytes is not None and (
        not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0
    ):
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.size_bytes must be a non-negative integer"
        )
    return result
'''
    new = '''def _lineage_artifact_metadata_identity(
    value: object, *, field: str, require_role: bool
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AuthenticatedEpistemicTransitionError(f"{field} must be an object")
    validated = _validated_lineage_artifact_fields(
        value, field=field, require_role=require_role
    )
    result: dict[str, Any] = {"sha256": validated["sha256"]}
    if require_role:
        result["role"] = validated["role"]
    # Paths, source-path annotations, and size are rebundling metadata rather than
    # graph-hop identity. The exact-key gate above rejects unknown nested claims,
    # while authority identity compares only exact checksum and required role.
    return result
'''
    text = replace_once(text, old, new, label="metadata identity contract")

    text = replace_once(
        text,
        '''        "base_graph_artifact": _lineage_artifact_metadata_identity(
            value.get("base_graph_artifact"), field=f"{field}.base_graph_artifact"
        ),
        "proposal_artifact": _lineage_artifact_metadata_identity(
            value.get("proposal_artifact"), field=f"{field}.proposal_artifact"
        ),
        "verification_decision_artifact": _lineage_artifact_metadata_identity(
            value.get("verification_decision_artifact"),
            field=f"{field}.verification_decision_artifact",
        ),
        "result_artifact_snapshots": [
            _lineage_artifact_metadata_identity(
                item, field=f"{field}.result_artifact_snapshots[{index}]"
            )
''',
        '''        "base_graph_artifact": _lineage_artifact_metadata_identity(
            value.get("base_graph_artifact"),
            field=f"{field}.base_graph_artifact",
            require_role=False,
        ),
        "proposal_artifact": _lineage_artifact_metadata_identity(
            value.get("proposal_artifact"),
            field=f"{field}.proposal_artifact",
            require_role=False,
        ),
        "verification_decision_artifact": _lineage_artifact_metadata_identity(
            value.get("verification_decision_artifact"),
            field=f"{field}.verification_decision_artifact",
            require_role=True,
        ),
        "result_artifact_snapshots": [
            _lineage_artifact_metadata_identity(
                item,
                field=f"{field}.result_artifact_snapshots[{index}]",
                require_role=True,
            )
''',
        label="metadata identity contexts",
    )

    SOURCE.write_text(text, encoding="utf-8")

    TESTS.write_text('''from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
)


def _artifact(*, with_role: bool = False, extended: bool = True) -> dict[str, object]:
    value: dict[str, object] = {
        "path": "provenance/inherited/base.json",
        "sha256": "a" * 64,
    }
    if extended:
        value.update(
            {
                "source_path": "/original/base.json",
                "source_path_authoritative": False,
                "size_bytes": 123,
            }
        )
    if with_role:
        value["role"] = "primary_result"
    return value


def test_nested_artifact_authority_claim_fails_closed() -> None:
    value = _artifact()
    value["credential_verified"] = True
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="inherited artifact key contract",
    ):
        module._validated_lineage_artifact_fields(
            value, field="lineage.base_graph_artifact", require_role=False
        )


def test_nested_role_artifact_unknown_scientific_claim_fails_closed() -> None:
    value = _artifact(with_role=True)
    value["scientific_authority_applied"] = True
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="inherited artifact key contract",
    ):
        module._lineage_artifact_metadata_identity(
            value,
            field="lineage.result_artifact_snapshots[0]",
            require_role=True,
        )


def test_minimal_historical_artifact_contract_remains_compatible() -> None:
    base = module._validated_lineage_artifact_fields(
        _artifact(extended=False),
        field="lineage.base_graph_artifact",
        require_role=False,
    )
    result = module._validated_lineage_artifact_fields(
        _artifact(with_role=True, extended=False),
        field="lineage.result_artifact_snapshots[0]",
        require_role=True,
    )
    assert set(base) == {"path", "sha256"}
    assert set(result) == {"path", "sha256", "role"}


def test_known_portability_fields_are_validated_without_becoming_authority_identity() -> None:
    value = _artifact(with_role=True)
    validated = module._validated_lineage_artifact_fields(
        value, field="lineage.result_artifact_snapshots[0]", require_role=True
    )
    assert set(validated) == {
        "path",
        "source_path",
        "source_path_authoritative",
        "sha256",
        "size_bytes",
        "role",
    }
    assert validated["source_path_authoritative"] is False
    identity = module._lineage_artifact_metadata_identity(
        value,
        field="lineage.result_artifact_snapshots[0]",
        require_role=True,
    )
    assert identity == {"sha256": "a" * 64, "role": "primary_result"}
''', encoding="utf-8")


if __name__ == "__main__":
    main()
