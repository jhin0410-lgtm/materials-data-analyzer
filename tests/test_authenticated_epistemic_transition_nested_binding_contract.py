from __future__ import annotations

import pytest

from materials_data_analyzer.research_loop import (
    authenticated_epistemic_transition as module,
)
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
