from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
PORTABILITY = Path("tests/test_authenticated_epistemic_transition_inherited_portability.py")
MERGE_GATE = Path("tests/test_authenticated_epistemic_transition_merge_gate.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_once_after(
    text: str,
    marker: str,
    old: str,
    new: str,
    *,
    label: str,
) -> str:
    marker_index = text.index(marker)
    prefix = text[:marker_index]
    suffix = text[marker_index:]
    count = suffix.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match after marker, found {count}")
    return prefix + suffix.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    parsed_enclosing = _json_object_from_exact_bytes(\n        enclosing_graph_bytes, field="enclosing_graph"\n    )\n    if parsed_enclosing != dict(enclosing_graph):\n        raise AuthenticatedEpistemicTransitionError(\n            "enclosing graph object diverges from its exact authenticated bytes"\n        )\n''',
        '''    parsed_enclosing = _json_object_from_exact_bytes(\n        enclosing_graph_bytes, field="enclosing_graph"\n    )\n''',
        label="use immutable exact enclosing bytes as chain anchor",
    )
    text = replace_once(
        text,
        '''        else:\n            successor = enclosing_graph\n            successor_bytes = enclosing_graph_bytes\n            successor_sha = canonical_enclosing_sha\n''',
        '''        else:\n            successor = parsed_enclosing\n            successor_bytes = enclosing_graph_bytes\n            successor_sha = canonical_enclosing_sha\n''',
        label="final chain successor uses exact parsed enclosing graph",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_portability() -> None:
    text = PORTABILITY.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            {\n                "node_id": "hypothesis-1",\n                "node_type": "hypothesis",\n                "statement": "The bounded structural target holds.",\n                "metadata": {"claim_scope": "structural"},\n            }\n        ],\n        "edges": [],\n''',
        '''            {\n                "node_id": "hypothesis-1",\n                "node_type": "hypothesis",\n                "statement": "The bounded structural target holds.",\n                "metadata": {"claim_scope": "structural"},\n            },\n            {\n                "node_id": "legacy-result-node",\n                "node_type": "analysis",\n                "statement": "A legacy verified analysis remains inherited authority.",\n                "execution_status": "completed",\n                "artifact_bindings": [\n                    {\n                        "role": "primary_result",\n                        "path": str(legacy_result),\n                        "sha256": legacy_result_sha,\n                    }\n                ],\n                "metadata": {"result_origin": "authorized_local_analysis"},\n            },\n        ],\n        "edges": [\n            {\n                "edge_id": "legacy-support",\n                "source_node_id": "legacy-result-node",\n                "target_node_id": "hypothesis-1",\n                "relation": "supports",\n                "assessment_level": "domain_verified",\n                "rationale": "Legacy v1.0-era verified structural support.",\n                "active": True,\n                "verification_artifact": {\n                    "role": "domain_verification_decision",\n                    "path": str(legacy_verifier),\n                    "sha256": legacy_verifier_sha,\n                },\n            }\n        ],\n''',
        label="legacy authority belongs to historical parent graph",
    )
    text = replace_once_after(
        text,
        "    base_graph = {",
        '            old_parent_graph["nodes"][0],\n',
        '            *old_parent_graph["nodes"],\n',
        label="inherit all historical parent nodes",
    )
    duplicate_legacy_node = '''            {\n                "node_id": "legacy-result-node",\n                "node_type": "analysis",\n                "statement": "A legacy verified analysis remains inherited authority.",\n                "execution_status": "completed",\n                "artifact_bindings": [\n                    {\n                        "role": "primary_result",\n                        "path": str(legacy_result),\n                        "sha256": legacy_result_sha,\n                    }\n                ],\n                "metadata": {"result_origin": "authorized_local_analysis"},\n            },\n'''
    text = replace_once_after(
        text,
        "    base_graph = {",
        duplicate_legacy_node,
        "",
        label="remove successor duplicate legacy node",
    )
    text = replace_once_after(
        text,
        "    base_graph = {",
        '''        "edges": [\n            {\n                "edge_id": "old-tests",\n''',
        '''        "edges": [\n            *old_parent_graph["edges"],\n            {\n                "edge_id": "old-tests",\n''',
        label="inherit all historical parent edges",
    )
    duplicate_legacy_edge = '''            {\n                "edge_id": "legacy-support",\n                "source_node_id": "legacy-result-node",\n                "target_node_id": "hypothesis-1",\n                "relation": "supports",\n                "assessment_level": "domain_verified",\n                "rationale": "Legacy v1.0-era verified structural support.",\n                "active": True,\n                "verification_artifact": {\n                    "role": "domain_verification_decision",\n                    "path": str(legacy_verifier),\n                    "sha256": legacy_verifier_sha,\n                },\n            },\n'''
    text = replace_once_after(
        text,
        "    base_graph = {",
        duplicate_legacy_edge,
        "",
        label="remove successor duplicate legacy edge",
    )
    PORTABILITY.write_text(text, encoding="utf-8")


def patch_merge_gate() -> None:
    text = MERGE_GATE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'match="base_graph_artifact must be an object",',
        'match="exact producer lineage key set",',
        label="malformed lineage now fails at exact key contract",
    )
    MERGE_GATE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_portability()
    patch_merge_gate()
