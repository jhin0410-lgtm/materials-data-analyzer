from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from materials_data_analyzer.research_loop import public_recursive_api as api


def _load_replay_driver() -> ModuleType:
    path = Path(__file__).with_name("test_public_recursive_real_evidence_replay.py")
    spec = importlib.util.spec_from_file_location("public_recursive_real_evidence_driver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load public recursive replay acceptance driver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def review_replay(tmp_path_factory: pytest.TempPathFactory) -> tuple[ModuleType, dict]:
    module = _load_replay_driver()
    fixture_builder = getattr(module.replay, "__wrapped__", None)
    if fixture_builder is None:
        raise RuntimeError("replay fixture lost its underlying deterministic builder")
    state = fixture_builder(tmp_path_factory)
    return module, state


def test_resigned_progression_cannot_replace_reconstructed_execution_truth(
    review_replay: tuple[ModuleType, dict],
) -> None:
    module, state = review_replay
    tampered = copy.deepcopy(state["progression1"])
    tampered["verified_execution"]["execution_outcome"] = "failed"
    tampered["verified_execution"]["execution_success"] = False
    tampered["progression_sha256"] = module._canonical_sha(
        tampered,
        "progression_sha256",
    )

    with pytest.raises(
        api.PublicRecursiveProgressionError,
        match="execution|reconstruction|persisted",
    ):
        api.validate_public_recursive_progression(
            tampered,
            validated_planning_context=state["context1"],
            recursive_limits=state["limits"],
        )


def test_rediagnosis_rejects_same_target_on_substituted_successor_graph(
    review_replay: tuple[ModuleType, dict],
) -> None:
    _, state = review_replay
    substituted = copy.deepcopy(state["graph2"])
    substituted["review_probe_non_scientific_metadata"] = "substituted"

    with pytest.raises(
        api.PublicRecursiveProgressionError,
        match="authenticated successor graph",
    ):
        api.complete_recursive_cycle_with_rediagnosis(
            validated_planning_context=state["context1"],
            progression=state["progression1"],
            current_discrepancy_report=state["report2"],
            previous_discrepancy_report=state["report1"],
            evaluated_graph=substituted,
            recursive_limits=state["limits"],
        )


def test_successor_public_context_inherits_nondefault_predecessor_limits_when_omitted(
    review_replay: tuple[ModuleType, dict],
) -> None:
    _, state = review_replay
    rebuilt = api.build_public_recursive_planning_context(
        validated_planning_artifact=state["planning2"],
        planning_handoff=state["handoff2"],
        source_discrepancy_report=state["report2"],
        source_evaluated_graph=state["graph2"],
        fresh_plan=state["plan2"],
        planner_program_state=state["program2"],
        previous_discrepancy_report=state["report1"],
        previous_validated_planning_context=state["context1"],
    )
    validated = api.validate_public_recursive_planning_context(rebuilt)
    assert validated["recursive_limits"] == state["limits"]
