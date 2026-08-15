from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_transition_consumer.py")
TESTS = Path("tests/test_authenticated_transition_consumer.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .kernel import ResearchLoopError\n",
        "from .epistemic_graph import EpistemicGraphError, validate_epistemic_graph\nfrom .kernel import ResearchLoopError\n",
        "epistemic-graph-import",
    )

    marker = "def _lineage_records(metadata: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:\n"
    helper = '''def _validate_graph_contract(\n    value: Mapping[str, Any], *, root: Path, field: str\n) -> None:\n    try:\n        validate_epistemic_graph(\n            value,\n            program_state={"workstreams": []},\n            artifact_root=root,\n        )\n    except EpistemicGraphError as exc:\n        raise AuthenticatedTransitionConsumerError(\n            f"{field} violates the epistemic graph contract"\n        ) from exc\n\n\n'''
    text = replace_once(text, marker, helper + marker, "graph-contract-helper")

    old = '''    _validate_inference_scope(\n        proposal=proposal,\n        inference_scope=str(recomputed["inference_scope"]),\n        target_claim_scope=target_scope,\n    )\n    _verify_successor_is_exact_append(\n        base_graph=base_graph,\n        successor_graph=graph,\n        proposal=proposal,\n    )\n    _verify_graph_realization(\n        graph,\n        proposal=proposal,\n        binding=recomputed,\n        result_snapshots=result_bindings,\n    )\n    graph_id = _text(graph.get("graph_id"), "epistemic graph graph_id")\n'''
    new = '''    _validate_inference_scope(\n        proposal=proposal,\n        inference_scope=str(recomputed["inference_scope"]),\n        target_claim_scope=target_scope,\n    )\n    _validate_graph_contract(\n        base_graph, root=root, field="current exact base graph snapshot"\n    )\n    _verify_successor_is_exact_append(\n        base_graph=base_graph,\n        successor_graph=graph,\n        proposal=proposal,\n    )\n    _verify_graph_realization(\n        graph,\n        proposal=proposal,\n        binding=recomputed,\n        result_snapshots=result_bindings,\n    )\n    _validate_graph_contract(graph, root=root, field="epistemic graph")\n    graph_id = _text(graph.get("graph_id"), "epistemic graph graph_id")\n'''
    text = replace_once(text, old, new, "late-graph-validation")
    SOURCE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    text += '''\n\ndef test_consumer_rejects_successor_that_violates_graph_schema_even_when_manifest_hash_is_synced(\n    tmp_path: Path,\n) -> None:\n    bundle = _make_bundle(tmp_path)\n    graph = _load_json(bundle / "epistemic_graph.json")\n    graph["unauthenticated_authority_override"] = True\n    _rewrite_graph_and_sync_manifest(bundle, graph)\n\n    with pytest.raises(\n        AuthenticatedTransitionConsumerError,\n        match="epistemic graph contract",\n    ):\n        authenticate_transition_bundle(bundle)\n'''
    TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
