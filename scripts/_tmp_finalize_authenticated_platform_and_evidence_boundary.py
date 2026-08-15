from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/authenticated_epistemic_transition.py")
TEST = Path("tests/test_authenticated_epistemic_transition.py")
DOC = Path("docs/AUTHENTICATED_EPISTEMIC_TRANSITION.md")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "access to that staging parent. No provenance or security claim should be read as resisting such\na same-identity attacker.\n",
        "access to that staging parent. No provenance or security claim should be read as resisting such\na same-identity attacker. Atomic publication for this producer is currently supported only on\nWindows and Linux; other platforms fail closed before transition inputs are consumed.\n",
        label="module platform boundary",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.5"',
        'AUTHENTICATED_TRANSITION_POLICY_VERSION = "2.6"',
        label="policy version",
    )
    text = replace_once(
        text,
        'AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE = "authenticated_domain_verification_decision"\n',
        'AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE = "authenticated_domain_verification_decision"\nAUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS = ("linux", "windows")\n',
        label="supported platforms constant",
    )
    class_block = '''class AuthenticatedEpistemicTransitionError(EpistemicTransitionError):\n    """Raised when authenticated transition production cannot preserve provenance."""\n\n\n'''
    helper = class_block + '''def _require_supported_publication_platform(\n    *,\n    os_name: str | None = None,\n    platform: str | None = None,\n) -> str:\n    actual_os_name = os.name if os_name is None else os_name\n    actual_platform = sys.platform if platform is None else platform\n    if actual_os_name == "nt":\n        return "windows"\n    if actual_platform.startswith("linux"):\n        return "linux"\n    raise AuthenticatedEpistemicTransitionError(\n        "authenticated transition publication currently supports only Windows and Linux "\n        "because another platform-safe atomic no-replace directory primitive has not been "\n        "implemented"\n    )\n\n\n'''
    text = replace_once(text, class_block, helper, label="publication platform preflight")
    text = replace_once(
        text,
        '''    for node_index, node in enumerate(raw_nodes):\n        if not isinstance(node, dict):\n            continue\n        raw_bindings = node.get("artifact_bindings")\n''',
        '''    for node_index, node in enumerate(raw_nodes):\n        if not isinstance(node, dict):\n            continue\n        if node.get("node_type") == "evidence":\n            raise AuthenticatedEpistemicTransitionError(\n                "authenticated self-contained transition does not yet accept inherited "\n                "evidence nodes because evidence_binding lacks a first-class checksum-bound "\n                "resolvable artifact contract"\n            )\n        raw_bindings = node.get("artifact_bindings")\n''',
        label="inherited evidence fail closed",
    )
    text = replace_once(
        text,
        '''    """Produce an authenticated diagnostic bundle under exclusive staging ownership.\n\n    The filesystem integrity boundary assumes no hostile same-OS-identity process can write\n    into or replace this function's private staging tree while it is being assembled.\n    """\n    base_path = Path(base_graph_path).expanduser().resolve(strict=True)\n''',
        '''    """Produce an authenticated diagnostic bundle under exclusive staging ownership.\n\n    The filesystem integrity boundary assumes no hostile same-OS-identity process can write\n    into or replace this function's private staging tree while it is being assembled.\n    Publication is intentionally limited to Windows and Linux until another platform-safe\n    atomic no-replace directory primitive is implemented.\n    """\n    publication_platform = _require_supported_publication_platform()\n    base_path = Path(base_graph_path).expanduser().resolve(strict=True)\n''',
        label="early platform preflight",
    )
    text = replace_once(
        text,
        '''            "transition_id": transition_id,\n            "bundle_artifact_root": ".",\n''',
        '''            "transition_id": transition_id,\n            "bundle_artifact_root": ".",\n            "publication_platform": publication_platform,\n            "supported_publication_platforms": list(\n                AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS\n            ),\n''',
        label="manifest platform fields",
    )
    text = replace_once(
        text,
        '''                "bundle_published_with_no_replace": True,\n                "bundle_relative_artifact_paths": True,\n                "inherited_artifacts_snapshotted": True,\n''',
        '''                "bundle_published_with_no_replace": True,\n                "unsupported_publication_platforms_fail_closed": True,\n                "bundle_relative_artifact_paths": True,\n                "inherited_artifacts_snapshotted": True,\n                "inherited_evidence_nodes_without_resolvable_artifacts_allowed": False,\n''',
        label="manifest boundary flags",
    )
    text = replace_once(
        text,
        '''    "AUTHENTICATED_TRANSITION_POLICY_VERSION",\n    "AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE",\n''',
        '''    "AUTHENTICATED_TRANSITION_POLICY_VERSION",\n    "AUTHENTICATED_TRANSITION_SUPPORTED_PUBLICATION_PLATFORMS",\n    "AUTHENTICATED_VERIFICATION_ARTIFACT_ROLE",\n''',
        label="public supported platform constant",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_test() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    assert result["bundle_artifact_root"] == "."\n    assert result["successor_graph"]["path"] == "epistemic_graph.json"\n''',
        '''    assert result["bundle_artifact_root"] == "."\n    assert result["publication_platform"] in {"linux", "windows"}\n    assert result["supported_publication_platforms"] == ["linux", "windows"]\n    assert boundary["unsupported_publication_platforms_fail_closed"] is True\n    assert boundary["inherited_evidence_nodes_without_resolvable_artifacts_allowed"] is False\n    assert result["successor_graph"]["path"] == "epistemic_graph.json"\n''',
        label="manifest platform/evidence assertions",
    )
    anchor = '''def test_v10_verifier_cannot_enter_authenticated_transition_path(tmp_path: Path) -> None:\n'''
    additions = '''def test_publication_platform_contract_is_explicit_and_fail_closed() -> None:\n    assert module._require_supported_publication_platform(\n        os_name="nt", platform="win32"\n    ) == "windows"\n    assert module._require_supported_publication_platform(\n        os_name="posix", platform="linux"\n    ) == "linux"\n    with pytest.raises(\n        AuthenticatedEpistemicTransitionError,\n        match="currently supports only Windows and Linux",\n    ):\n        module._require_supported_publication_platform(\n            os_name="posix", platform="darwin"\n        )\n\n\ndef test_inherited_evidence_nodes_fail_closed_without_resolvable_artifact_contract(\n    tmp_path: Path,\n) -> None:\n    base = _base_graph()\n    nodes = base["nodes"]\n    assert isinstance(nodes, list)\n    nodes.append(\n        {\n            "node_id": "evidence-1",\n            "node_type": "evidence",\n            "statement": "Hash-only inherited evidence.",\n            "evidence_binding": {\n                "workstream_id": "benchmark",\n                "role": "measured_source",\n                "sha256": "e" * 64,\n            },\n        }\n    )\n    with pytest.raises(\n        AuthenticatedEpistemicTransitionError,\n        match="does not yet accept inherited evidence nodes",\n    ):\n        module._remap_base_graph_artifacts(\n            base,\n            artifact_root=tmp_path,\n            payloads={},\n        )\n\n\n'''
    if additions.strip() in text:
        raise RuntimeError("platform/evidence regression additions already present")
    text = replace_once(text, anchor, additions + anchor, label="platform/evidence regressions")
    TEST.write_text(text, encoding="utf-8")


def write_doc() -> None:
    if DOC.exists():
        raise RuntimeError(f"documentation already exists: {DOC}")
    DOC.write_text(
        '''# Authenticated Epistemic Transition Producer\n\nThe authenticated transition producer binds the exact bytes of a transition proposal and a\ndomain-verification decision v1.1 to an exact directional `inference_edge_id`. It emits that\nrelation as **diagnostic only**. The producer does not make the relation scientifically true,\ndoes not authorize execution, and does not grant stop/reframe or positive-closeout authority.\n\n## Publication platforms\n\nAtomic no-replace publication is currently supported only on **Windows and Linux**. The public\nproducer fails closed on other operating systems before transition inputs are consumed. This is\na feature-level restriction; the rest of `materials-data-analyzer` is not thereby declared\nWindows/Linux-only. Adding another platform requires a platform-safe atomic no-replace directory\npublication primitive plus regression coverage.\n\n## Filesystem trust boundary\n\nThe producer assumes exclusive write ownership of its private staging tree from creation through\npublication. It is not a sandbox against a hostile process sharing the same OS identity and write\naccess to that staging parent/tree. No same-identity concurrent-tamper resistance is claimed.\n\n## Inherited provenance\n\nInherited authenticated lineage is re-authenticated from its exact snapshotted base/proposal/\nverifier bytes before republishing. The stored binding must equal the recomputed binding, artifact\nhashes must be canonical SHA-256 text, and result snapshot role/hash identities must match the\nexact proposal. This establishes byte/identity coherence only; `verifier_id` remains free text and\nno institutional credential authority is inferred.\n\n## Evidence-node limitation\n\nInherited `evidence` nodes are currently rejected. Their existing `evidence_binding` contract is\nworkstream/role/SHA only and has no first-class resolvable artifact path/origin binding, so the\nproducer cannot make those nodes self-contained without inventing provenance. A later evidence\norigin contract must provide checksum-bound resolvable artifacts before this restriction can be\nremoved. The same principle is why new `empirical_derived` authenticated transitions remain\nfail-closed in this producer.\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_source()
    patch_test()
    write_doc()
