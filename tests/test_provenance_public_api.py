from __future__ import annotations

from materials_data_analyzer import research_loop


def test_origin_and_authenticated_critic_public_api_exports() -> None:
    assert research_loop.EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION == "1.0"
    assert research_loop.PROGRAM_EVIDENCE_ORIGIN_BINDING_SCHEMA_VERSION == "1.0"
    assert research_loop.AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION == "1.0"
    assert callable(research_loop.authenticate_evidence_origin_binding)
    assert callable(research_loop.authenticate_program_evidence_origin_binding)
    assert callable(research_loop.build_authenticated_scientific_critic_report)


def test_public_api_does_not_alias_authenticated_critic_over_base_critic() -> None:
    assert research_loop.build_scientific_critic_report is not (
        research_loop.build_authenticated_scientific_critic_report
    )
