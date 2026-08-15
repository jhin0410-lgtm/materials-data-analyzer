from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop import (
    authenticated_epistemic_transition as module,
)
from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
)


def test_current_base_duplicate_normalized_artifact_roles_fail_closed() -> None:
    base = {
        "nodes": [
            {
                "node_id": "result-1",
                "artifact_bindings": [
                    {"role": " primary_result ", "sha256": "a" * 64},
                    {"role": "primary_result", "sha256": "b" * 64},
                ],
            }
        ],
        "edges": [],
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="duplicate normalized role: primary_result",
    ):
        module._assert_current_base_artifact_hashes_canonical(base)


def test_padded_inherited_evidence_node_type_still_fails_closed(tmp_path) -> None:
    base = {
        "schema_version": "1.0",
        "graph_id": "graph-1",
        "research_scope": "evidence provenance boundary",
        "nodes": [
            {
                "node_id": "evidence-1",
                "node_type": " evidence ",
                "statement": "Hash-only evidence remains unresolved.",
            }
        ],
        "edges": [],
    }
    raw = (json.dumps(base, sort_keys=True) + "\n").encode("utf-8")
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="does not yet accept inherited evidence nodes",
    ):
        module._remap_base_graph_artifacts(
            base,
            enclosing_graph_bytes=raw,
            enclosing_graph_sha256=hashlib.sha256(raw).hexdigest(),
            program_state={"workstreams": []},
            artifact_root=tmp_path,
            payloads={},
        )


def test_domain_verified_authority_count_normalizes_accepted_enum_text() -> None:
    base = {
        "edges": [
            {
                "active": True,
                "assessment_level": " domain_verified ",
                "relation": " supports ",
            },
            {
                "active": True,
                "assessment_level": "diagnostic",
                "relation": "contradicts",
            },
        ]
    }
    assert module._inherited_domain_verified_relation_count(base) == 1


def test_authenticated_hop_rejects_graph_level_metadata_rewrite() -> None:
    base = {
        "graph_id": "graph-v1",
        "metadata": {
            "audit_context": {"owner": "original", "sequence": 1},
            "transition_lineage": [],
            "authenticated_transition_lineage": [],
        },
    }
    successor = {
        "graph_id": "graph-v2",
        "metadata": {
            "audit_context": {"owner": "grafted", "sequence": 1},
            "transition_lineage": [],
            "authenticated_transition_lineage": [],
        },
    }
    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="rewrites graph-level metadata outside transition lineage",
    ):
        module._assert_transition_metadata_append_only(
            base_graph=base,
            successor_graph=successor,
            authenticated_record={},
            proposal={},
            base_graph_sha256="a" * 64,
            field="regression",
        )
