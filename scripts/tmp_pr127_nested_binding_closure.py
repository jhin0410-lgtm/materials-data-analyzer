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
    replacement = anchor + '''_LINEAGE_ARTIFACT_KEYS = frozenset(
    {"path", "source_path", "source_path_authoritative", "sha256", "size_bytes"}
)
_LINEAGE_ROLE_ARTIFACT_KEYS = _LINEAGE_ARTIFACT_KEYS | {"role"}
'''
    text = replace_once(text, anchor, replacement, label="artifact-key-constants")

    marker = '\ndef _snapshot_lineage_binding(\n'
    if text.count(marker) != 1:
        raise SystemExit(f"sanitizer insertion anchor count={text.count(marker)}")
    helper = r'''

def _validated_lineage_artifact_fields(
    raw: Mapping[str, Any], *, field: str, require_role: bool
) -> dict[str, Any]:
    expected_keys = _LINEAGE_ROLE_ARTIFACT_KEYS if require_role else _LINEAGE_ARTIFACT_KEYS
    raw_keys = set(raw)
    if raw_keys != expected_keys:
        unknown = sorted(raw_keys - expected_keys)
        missing = sorted(expected_keys - raw_keys)
        raise AuthenticatedEpistemicTransitionError(
            f"{field} must use the exact producer artifact key set; "
            f"unknown={unknown}, missing={missing}"
        )
    path = _lineage_identity(raw, "path")
    source_path = _lineage_identity(raw, "source_path")
    sha256 = _lineage_sha256(raw, "sha256")
    if raw.get("source_path_authoritative") is not False:
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.source_path_authoritative must be false"
        )
    size_bytes = raw.get("size_bytes")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise AuthenticatedEpistemicTransitionError(
            f"{field}.size_bytes must be a non-negative integer"
        )
    result: dict[str, Any] = {
        "path": path,
        "source_path": source_path,
        "source_path_authoritative": False,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    if require_role:
        result["role"] = _lineage_identity(raw, "role")
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
    new = '''    require_role = "role" in raw
    copied = _validated_lineage_artifact_fields(
        raw, field=field, require_role=require_role
    )
    copied["path"] = bundle_path
    copied["source_path"] = str(source)
    copied["sha256"] = actual_sha
    copied["size_bytes"] = len(data)
    return copied
'''
    if text.count(old) != 1:
        raise SystemExit(f"snapshot-lineage reconstruction anchor count={text.count(old)}")
    text = text.replace(old, new, 1)

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
    new = '''    require_role = "role" in raw
    copied = _validated_lineage_artifact_fields(
        raw, field=field, require_role=require_role
    )
    copied["path"] = bundle_path
    copied["source_path"] = str(source)
    copied["sha256"] = actual_sha
    copied["size_bytes"] = len(data)
    return copied, data
'''
    text = replace_once(text, old, new, label="captured-lineage reconstruction")

    old = '''    result: dict[str, Any] = {"sha256": _lineage_sha256(value, "sha256")}
    if "role" in value:
        result["role"] = _lineage_identity(value, "role")
    # Paths, source-path annotations, and size are rebundling metadata rather than
'''
    new = '''    require_role = "role" in value
    validated = _validated_lineage_artifact_fields(
        value, field=field, require_role=require_role
    )
    result: dict[str, Any] = {"sha256": validated["sha256"]}
    if require_role:
        result["role"] = validated["role"]
    # Paths, source-path annotations, and size are rebundling metadata rather than
'''
    text = replace_once(text, old, new, label="metadata identity exact keys")

    SOURCE.write_text(text, encoding="utf-8")

    TESTS.write_text('''from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop import authenticated_epistemic_transition as module
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
)


def _artifact(*, with_role: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "path": "provenance/inherited/base.json",
        "source_path": "/original/base.json",
        "source_path_authoritative": False,
        "sha256": "a" * 64,
        "size_bytes": 123,
    }
    if with_role:
        value["role"] = "primary_result"
    return value


def test_nested_artifact_authority_claim_fails_closed() -> None:
    value = _artifact()
    value["credential_verified"] = True
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="exact producer artifact key set",
    ):
        module._validated_lineage_artifact_fields(
            value, field="lineage.base_graph_artifact", require_role=False
        )


def test_nested_role_artifact_unknown_scientific_claim_fails_closed() -> None:
    value = _artifact(with_role=True)
    value["scientific_authority_applied"] = True
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="exact producer artifact key set",
    ):
        module._lineage_artifact_metadata_identity(
            value, field="lineage.result_artifact_snapshots[0]"
        )


def test_exact_nested_artifact_contract_preserves_only_portability_fields() -> None:
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
''', encoding="utf-8")


if __name__ == "__main__":
    main()
