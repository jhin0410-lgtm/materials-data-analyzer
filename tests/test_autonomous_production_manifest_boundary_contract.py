from __future__ import annotations

import ast
import inspect
import textwrap

from materials_data_analyzer.research_loop import autonomous_production_driver


def test_base_manifest_explicitly_denies_paper_evidence_row_level_authority() -> None:
    """The producer must persist the boundary explicitly; absence is not equivalent to False."""

    source = textwrap.dedent(
        inspect.getsource(autonomous_production_driver.run_autonomous_production)
    )
    tree = ast.parse(source)
    manifest_assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "manifest"
    )
    assert isinstance(manifest_assignment.value, ast.Dict)

    literal_entries: dict[str, object] = {}
    for key, value in zip(
        manifest_assignment.value.keys,
        manifest_assignment.value.values,
        strict=True,
    ):
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(value, ast.Constant)
        ):
            literal_entries[key.value] = value.value

    assert "paper_evidence_promoted_to_row_level_authority" in literal_entries
    assert literal_entries["paper_evidence_promoted_to_row_level_authority"] is False
