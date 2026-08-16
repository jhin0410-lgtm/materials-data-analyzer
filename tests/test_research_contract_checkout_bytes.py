from __future__ import annotations

from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_provenance_bound_research_contracts_checkout_with_lf_bytes() -> None:
    root = _root()
    attributes = (root / ".gitattributes").read_text(encoding="utf-8")
    assert "configs/research/*.json text eol=lf" in attributes

    critical = (
        "configs/research/nist_ambench_stage1_structural_mission.v1.json",
        "configs/research/nist_ambench_stage1_request_delegation_policy.v1.json",
        "configs/research/nist_ambench_stage1_action_registry.v1.json",
        "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json",
        "configs/research/nist_ambench_stage1_research_objective.v1.json",
    )
    for relative in critical:
        raw = (root / relative).read_bytes()
        assert b"\r\n" not in raw, f"Git checkout changed exact bytes for {relative}"
