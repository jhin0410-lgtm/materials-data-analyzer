from __future__ import annotations

from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.authorized_execution as execution


@pytest.mark.parametrize(
    "entrypoint",
    [
        execution.execute_authorized_action,
        execution.execute_authorized_action_with_failure_classification,
    ],
)
def test_nist_action_cannot_enter_nasa_execution_surface(
    tmp_path: Path,
    entrypoint,
) -> None:
    """Both public execution entrypoints must reject the cross-adapter route pre-I/O."""
    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="NIST structural action cannot be routed through the NASA adapter",
    ):
        entrypoint(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=tmp_path / "missing-run",
            action_registry_path=tmp_path / "missing-registry.json",
            request_path=tmp_path / "missing-request.json",
            expected_action_type="nist_structural_design_simulation",
        )


def test_legacy_execution_internal_namespace_remains_visible() -> None:
    """The NIST facade must not hide long-standing NASA compatibility seams."""
    assert execution.PROTOCOL_ACTION_TYPE == "protocol_stratification"
    assert callable(execution._dispatch_cost_units)
    assert isinstance(execution._DISPATCH, dict)
    assert callable(execution.load_research_state)
    assert callable(execution.assess_current_action_authorization)
