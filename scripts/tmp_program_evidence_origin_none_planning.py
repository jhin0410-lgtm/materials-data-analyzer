from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/program_evidence_origin_binding.py")
TESTS = Path("tests/test_program_evidence_origin_binding.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    source = replace_once(
        source,
        '''        planning_state = raw_workstream.get("planning_state")\n        if not isinstance(planning_state, Mapping):\n            raise ProgramEvidenceOriginBindingError(\n                f"program_state.workstreams[{index}].planning_state must be an object"\n            )\n        evidence_bindings = planning_state.get("evidence_bindings")\n''',
        '''        planning_state = raw_workstream.get("planning_state")\n        if planning_state is None:\n            # `build_research_program()` legitimately uses None for disabled or\n            # runtime-context-blocked workstreams; they contribute no evidence.\n            continue\n        if not isinstance(planning_state, Mapping):\n            raise ProgramEvidenceOriginBindingError(\n                f"program_state.workstreams[{index}].planning_state must be an object or null"\n            )\n        evidence_bindings = planning_state.get("evidence_bindings")\n''',
        "nullable-planning-state",
    )
    SOURCE.write_text(source, encoding="utf-8")

    tests = TESTS.read_text(encoding="utf-8")
    tests += '''\n\ndef test_accepts_unrelated_disabled_or_runtime_blocked_workstreams_with_null_planning_state() -> None:\n    program_state, binding, evidence, declaration, verification = _fixture()\n    workstreams = program_state["workstreams"]\n    assert isinstance(workstreams, list)\n    workstreams.extend(\n        [\n            {\n                "workstream_id": "ws-disabled",\n                "status": "disabled_by_mission",\n                "planning_state": None,\n            },\n            {\n                "workstream_id": "ws-runtime-needed",\n                "status": "runtime_context_required",\n                "planning_state": None,\n            },\n        ]\n    )\n    result = authenticate_program_evidence_origin_binding(\n        program_state=program_state,\n        program_evidence_binding=binding,\n        evidence_bytes=evidence,\n        origin_declaration_bytes=declaration,\n        origin_verification_decision_bytes=verification,\n    )\n    assert result["verified_program_state_membership_established"] is True\n'''
    TESTS.write_text(tests, encoding="utf-8")


if __name__ == "__main__":
    main()
