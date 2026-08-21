from __future__ import annotations

from pathlib import Path

REDIAGNOSIS = Path(
    "src/materials_data_analyzer/research_loop/recursive_research_cycle_rediagnosis.py"
)
TEST_EVIDENCE = Path("tests/test_recursive_research_cycle_evidence.py")
TEST_PLAN_VERIFIER = Path("tests/test_autonomous_inquiry_plan_verifier.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


rediagnosis = REDIAGNOSIS.read_text(encoding="utf-8")
old_validation = '''    verified = validate_physics_hardened_model_evidence_discrepancy_report(
        current,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
        previous_report=previous,
    )
'''
new_validation = '''    try:
        verified = validate_physics_hardened_model_evidence_discrepancy_report(
            current,
            evaluated_graph=graph,
            hypothesis_portfolio=portfolio,
            previous_report=previous,
        )
    except ModelEvidenceDiscrepancyPhysicsPolicyError as exc:
        raise RecursiveResearchRediagnosisError(
            "current discrepancy report failed physics/provenance-hardened validation"
        ) from exc
'''
rediagnosis = replace_once(
    rediagnosis,
    old_validation,
    new_validation,
    label="re-diagnosis physics-policy wrapper",
)
REDIAGNOSIS.write_text(rediagnosis, encoding="utf-8")


evidence_test = TEST_EVIDENCE.read_text(encoding="utf-8")
old_bundle_tail = '''    apply_authenticated_epistemic_transition_files(
        base_graph_path=base,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    return output, result_sha
'''
new_bundle_tail = '''    apply_authenticated_epistemic_transition_files(
        base_graph_path=base,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=tmp_path,
        output_dir=output,
    )
    # The authenticated successor graph retains historical artifact paths. Materialize
    # the exact bound historical bytes inside the published bundle so the independent
    # consumer can revalidate them rather than relying on the producer workspace.
    (output / "prior-result.json").write_bytes((tmp_path / "prior-result.json").read_bytes())
    (output / "prior-verifier.json").write_bytes(
        (tmp_path / "prior-verifier.json").read_bytes()
    )
    return output, result_sha
'''
evidence_test = replace_once(
    evidence_test,
    old_bundle_tail,
    new_bundle_tail,
    label="authenticated bundle historical artifacts",
)
TEST_EVIDENCE.write_text(evidence_test, encoding="utf-8")


verifier_test = TEST_PLAN_VERIFIER.read_text(encoding="utf-8")
old_handoff = '''def _handoff(previous_report_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "source_discrepancy_report_sha256": previous_report_sha,
'''
new_handoff = '''def _handoff(previous_report_sha: str) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": previous_report_sha,
'''
verifier_test = replace_once(
    verifier_test,
    old_handoff,
    new_handoff,
    label="validated recursive handoff policy fixture",
)
TEST_PLAN_VERIFIER.write_text(verifier_test, encoding="utf-8")
