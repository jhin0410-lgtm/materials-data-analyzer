from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop.authenticated_epistemic_transition import (
    AuthenticatedEpistemicTransitionError,
    _reject_transition_id_reuse,
)


def test_reused_transition_id_in_legacy_lineage_is_rejected() -> None:
    metadata = {
        "transition_lineage": [
            {
                "transition_id": "transition-1",
                "parent_graph_id": "graph-v0",
            }
        ]
    }

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="already exists in base transition_lineage",
    ):
        _reject_transition_id_reuse(metadata, transition_id="transition-1")


def test_padded_legacy_transition_id_cannot_bypass_reuse_check() -> None:
    metadata = {"transition_lineage": [{"transition_id": "  transition-1  "}]}

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="already exists in base transition_lineage: transition-1",
    ):
        _reject_transition_id_reuse(metadata, transition_id="transition-1")


def test_reused_transition_id_in_authenticated_lineage_is_rejected() -> None:
    metadata = {
        "authenticated_transition_lineage": [
            {
                "transition_id": "transition-1",
                "authenticated_inference_binding": {"inference_edge_id": "edge-old"},
            }
        ]
    }

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="already exists in base authenticated_transition_lineage",
    ):
        _reject_transition_id_reuse(metadata, transition_id="transition-1")


def test_preexisting_duplicate_lineage_is_rejected_even_when_padding_differs() -> None:
    metadata = {
        "transition_lineage": [
            {"transition_id": "transition-old"},
            {"transition_id": "  transition-old  "},
        ]
    }

    with pytest.raises(
        AuthenticatedEpistemicTransitionError,
        match="contains duplicate transition_id: transition-old",
    ):
        _reject_transition_id_reuse(metadata, transition_id="transition-new")


def test_fresh_transition_id_returns_existing_lineage_unchanged() -> None:
    legacy_record = {"transition_id": "transition-old"}
    authenticated_record = {"transition_id": "transition-auth-old"}
    metadata = {
        "transition_lineage": [legacy_record],
        "authenticated_transition_lineage": [authenticated_record],
    }

    legacy, authenticated = _reject_transition_id_reuse(
        metadata, transition_id="transition-new"
    )

    assert legacy == [legacy_record]
    assert authenticated == [authenticated_record]
