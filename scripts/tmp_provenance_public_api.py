from __future__ import annotations

from pathlib import Path

INIT = Path("src/materials_data_analyzer/research_loop/__init__.py")
DOC = Path("docs/EVIDENCE_ORIGIN_PROVENANCE.md")
TEST = Path("tests/test_provenance_public_api.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_init() -> None:
    text = INIT.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''from .authorized_execution import (\n    EXECUTION_POLICY_VERSION,\n''',
        '''from .evidence_origin_binding import (\n    EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION,\n    EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION,\n    EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION,\n    EVIDENCE_ORIGIN_VERIFICATION_SCOPE,\n    EvidenceOriginBindingError,\n    authenticate_evidence_origin_binding,\n)\nfrom .program_evidence_origin_binding import (\n    PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION,\n    ProgramEvidenceOriginBindingError,\n    authenticate_program_evidence_origin_binding,\n)\nfrom .authorized_execution import (\n    EXECUTION_POLICY_VERSION,\n''',
        "origin-imports",
    )
    text = replace_once(
        text,
        '''from .scientific_critic_policy import (\n    SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION,\n    build_policy_hardened_scientific_critic_report,\n)\n''',
        '''from .scientific_critic_policy import (\n    SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION,\n    build_policy_hardened_scientific_critic_report,\n)\nfrom .scientific_critic_authenticated_policy import (\n    AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION,\n    build_authenticated_scientific_critic_report,\n)\n''',
        "critic-import",
    )
    text = replace_once(
        text,
        '''    "EPISTEMIC_MULTICYCLE_SCHEMA_VERSION",\n    "EXECUTION_POLICY_VERSION",\n''',
        '''    "EPISTEMIC_MULTICYCLE_SCHEMA_VERSION",\n    "EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION",\n    "EVIDENCE_ORIGIN_DECLARATION_SCHEMA_VERSION",\n    "EVIDENCE_ORIGIN_VERIFICATION_SCHEMA_VERSION",\n    "EVIDENCE_ORIGIN_VERIFICATION_SCOPE",\n    "EXECUTION_POLICY_VERSION",\n''',
        "origin-constants-all",
    )
    text = replace_once(
        text,
        '''    "PROGRAM_POLICY_VERSION",\n    "PROGRAM_SCHEMA_VERSION",\n''',
        '''    "PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION",\n    "PROGRAM_POLICY_VERSION",\n    "PROGRAM_SCHEMA_VERSION",\n''',
        "bridge-constant-all",
    )
    text = replace_once(
        text,
        '''    "SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION",\n    "SCIENTIFIC_CRITIC_POLICY_VERSION",\n''',
        '''    "AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION",\n    "SCIENTIFIC_CRITIC_HARDENING_POLICY_VERSION",\n    "SCIENTIFIC_CRITIC_POLICY_VERSION",\n''',
        "critic-constant-all",
    )
    text = replace_once(
        text,
        '''    "EpistemicMultiCycleError",\n    "NasaActionPolicyError",\n''',
        '''    "EpistemicMultiCycleError",\n    "EvidenceOriginBindingError",\n    "NasaActionPolicyError",\n''',
        "origin-error-all",
    )
    text = replace_once(
        text,
        '''    "PlanningTransitionError",\n    "ResearchCycleError",\n''',
        '''    "PlanningTransitionError",\n    "ProgramEvidenceOriginBindingError",\n    "ResearchCycleError",\n''',
        "bridge-error-all",
    )
    text = replace_once(
        text,
        '''    "authenticate_transition_bundle",\n    "available_planning_adapters",\n''',
        '''    "authenticate_evidence_origin_binding",\n    "authenticate_program_evidence_origin_binding",\n    "authenticate_transition_bundle",\n    "available_planning_adapters",\n''',
        "origin-functions-all",
    )
    text = replace_once(
        text,
        '''    "build_scientific_critic_report",\n    "build_target_reference_sensitivity",\n''',
        '''    "build_authenticated_scientific_critic_report",\n    "build_scientific_critic_report",\n    "build_target_reference_sensitivity",\n''',
        "critic-function-all",
    )
    INIT.write_text(text, encoding="utf-8")


def write_doc() -> None:
    DOC.write_text('''# Evidence-origin provenance and authenticated critic APIs\n\nThis layer separates **provenance identity** from **scientific authority**.\n\n## Exact evidence-origin classification\n\n`authenticate_evidence_origin_binding(...)` binds three exact byte strings:\n\n1. evidence artifact bytes;\n2. an origin declaration;\n3. an origin-verification decision.\n\nA successful result authenticates only the recorded classification and its exact SHA-256 identities. It does **not** authenticate that a physical experiment actually occurred, the verifier's credentials, instrument calibration, result validity, source independence, empirical scientific authority, execution permission, or positive closeout.\n\n## Program evidence bridge\n\n`authenticate_program_evidence_origin_binding(...)` additionally requires an exact `{workstream_id, role, sha256}` binding to occur once in the supplied research-program state and requires the same SHA-256 to identify the exact evidence bytes used by the origin-classification primitive.\n\nThe bridge establishes membership in the **supplied** program state; it does not independently re-authenticate how that program state was produced. Disabled or runtime-context-blocked workstreams with `planning_state: null` contribute no evidence and are ignored. Malformed non-null planning states fail closed.\n\nThe bridge still does not grant empirical authority.\n\n## Authenticated Scientific Critic\n\n`build_authenticated_scientific_critic_report(...)` accepts a bundle root, independently re-authenticates the bundle, pins the exact graph SHA before and after base-critic evaluation, and may add a directional critic advisory. It does not accept caller-supplied consumer reports.\n\nAuthenticated support does not establish support independence or calibrated confidence. Authenticated contradiction/falsification may add a **manual, plan-only** reframe advisory, but cannot replace a stronger base-critic stop recommendation or automatically stop/execute anything.\n\nBoth `empirical_derived` and `empirical_direct` remain disabled at the critic adapter. The existence of an origin-classification record or program-evidence bridge is not sufficient by itself to reopen those scopes. A future transition contract must first snapshot resolvable origin-authenticated evidence into the bundle and independently re-authenticate it; physical-source/credential policy may still be required after that.\n\n## Public imports\n\n```python\nfrom materials_data_analyzer.research_loop import (\n    authenticate_evidence_origin_binding,\n    authenticate_program_evidence_origin_binding,\n    build_authenticated_scientific_critic_report,\n)\n```\n''', encoding="utf-8")


def write_test() -> None:
    TEST.write_text('''from __future__ import annotations\n\nimport materials_data_analyzer.research_loop as research_loop\n\n\ndef test_origin_and_authenticated_critic_public_api_exports() -> None:\n    assert research_loop.EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION == "1.0"\n    assert research_loop.PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION == "1.0"\n    assert research_loop.AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION == "1.0"\n    assert callable(research_loop.authenticate_evidence_origin_binding)\n    assert callable(research_loop.authenticate_program_evidence_origin_binding)\n    assert callable(research_loop.build_authenticated_scientific_critic_report)\n\n\ndef test_public_api_does_not_alias_authenticated_critic_over_base_critic() -> None:\n    assert research_loop.build_scientific_critic_report is not (\n        research_loop.build_authenticated_scientific_critic_report\n    )\n''', encoding="utf-8")


if __name__ == "__main__":
    patch_init()
    write_doc()
    write_test()
