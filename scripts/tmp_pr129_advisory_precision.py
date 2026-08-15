from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/scientific_critic_authenticated_policy.py")
TESTS = Path("tests/test_scientific_critic_authenticated_policy.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''def _validate_consumer_authority_boundary(consumer: Mapping[str, Any]) -> None:\n    if consumer.get("current_transition_exact_provenance_authenticated") is not True:\n''',
        '''def _validate_consumer_authority_boundary(consumer: Mapping[str, Any]) -> None:\n    if consumer.get("schema_version") != "1.0" or consumer.get("consumer_policy_version") != "1.0":\n        raise ScientificCriticError(\n            "authenticated critic adapter supports only transition consumer schema/policy 1.0"\n        )\n    if consumer.get("current_transition_exact_provenance_authenticated") is not True:\n''',
        "consumer-version-pin",
    )
    text = replace_once(
        text,
        '''    forbidden_true = (\n        "scientific_authority_applied",\n        "execution_authorized",\n''',
        '''    forbidden_true = (\n        "scientific_authority_applied",\n        "scientific_status_changed",\n        "execution_authorized",\n''',
        "scientific-status-boundary",
    )
    text = replace_once(
        text,
        '''    if consumer.get("inference_scope") == "empirical_derived":\n        raise ScientificCriticError(\n            "empirical_derived critic authority remains disabled until the evidence-origin contract is authenticated"\n        )\n''',
        '''    if consumer.get("inference_scope") in {"empirical_derived", "empirical_direct"}:\n        raise ScientificCriticError(\n            "empirical critic authority remains disabled until the evidence-origin contract is authenticated"\n        )\n''',
        "empirical-both-scopes",
    )
    text = replace_once(
        text,
        '''    target = _target_report_by_id(result, target_id)\n    advisory_applied = target is not None\n    if target is not None:\n''',
        '''    target = _target_report_by_id(result, target_id)\n    advisory_applied = target is not None\n    negative_manual_reframe = (\n        advisory_applied and str(consumer["relation"]) in _NEGATIVE_RELATIONS\n    )\n    if target is not None:\n''',
        "manual-reframe-condition",
    )
    text = replace_once(
        text,
        '''            "authenticated_directional_advisory_may_inform_manual_reframe": True,\n''',
        '''            "authenticated_directional_advisory_may_inform_manual_reframe": negative_manual_reframe,\n''',
        "manual-reframe-boundary",
    )
    text = replace_once(
        text,
        '''            "empirical_derived_authority_enabled_without_evidence_origin_contract": False,\n''',
        '''            "empirical_derived_authority_enabled_without_evidence_origin_contract": False,\n            "empirical_direct_authority_enabled_without_evidence_origin_contract": False,\n''',
        "empirical-direct-boundary",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    return {\n        "bundle_root": "/bundle",\n        "current_transition_exact_provenance_authenticated": True,\n''',
        '''    return {\n        "schema_version": "1.0",\n        "consumer_policy_version": "1.0",\n        "bundle_root": "/bundle",\n        "current_transition_exact_provenance_authenticated": True,\n''',
        "test-consumer-version",
    )
    text = replace_once(
        text,
        '''        "authority_boundary": {\n            "scientific_authority_applied": False,\n            "execution_authorized": False,\n''',
        '''        "authority_boundary": {\n            "scientific_authority_applied": False,\n            "scientific_status_changed": False,\n            "execution_authorized": False,\n''',
        "test-consumer-status",
    )
    text = replace_once(
        text,
        '''    assert "AUTHENTICATED_DIRECTIONAL_CONTRADICTION_PRESENT" in codes\n''',
        '''    assert "AUTHENTICATED_DIRECTIONAL_CONTRADICTION_PRESENT" in codes\n    assert (\n        result["autonomy_boundary"][\n            "authenticated_directional_advisory_may_inform_manual_reframe"\n        ]\n        is True\n    )\n''',
        "negative-reframe-assertion",
    )
    text = replace_once(
        text,
        '''    assert (\n        result["autonomy_boundary"][\n            "support_independence_established_by_exact_edge_provenance"\n        ]\n        is False\n    )\n''',
        '''    assert (\n        result["autonomy_boundary"][\n            "support_independence_established_by_exact_edge_provenance"\n        ]\n        is False\n    )\n    assert (\n        result["autonomy_boundary"][\n            "authenticated_directional_advisory_may_inform_manual_reframe"\n        ]\n        is False\n    )\n''',
        "support-no-reframe-assertion",
    )
    text = replace_once(
        text,
        '''    assert result["summary"]["authenticated_directional_advisories"] == 0\n''',
        '''    assert result["summary"]["authenticated_directional_advisories"] == 0\n    assert (\n        result["autonomy_boundary"][\n            "authenticated_directional_advisory_may_inform_manual_reframe"\n        ]\n        is False\n    )\n''',
        "filtered-no-reframe-assertion",
    )
    text += '''\n\ndef test_adapter_rejects_empirical_direct_even_if_consumer_regresses(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    _wire(\n        monkeypatch,\n        consumer=_consumer(relation="supports", scope="empirical_direct"),\n        base=_base_report(),\n    )\n    with pytest.raises(module.ScientificCriticError, match="evidence-origin contract"):\n        module.build_authenticated_scientific_critic_report(\n            tmp_path / "bundle", program_state={"generated_goals": []}\n        )\n\n\ndef test_adapter_rejects_unknown_consumer_contract_version(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    consumer = _consumer()\n    consumer["consumer_policy_version"] = "2.0"\n    _wire(monkeypatch, consumer=consumer, base=_base_report())\n    with pytest.raises(module.ScientificCriticError, match="schema/policy 1.0"):\n        module.build_authenticated_scientific_critic_report(\n            tmp_path / "bundle", program_state={"generated_goals": []}\n        )\n\n\ndef test_adapter_rejects_consumer_scientific_status_escalation(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    consumer = _consumer(relation="supports")\n    boundary = consumer["authority_boundary"]\n    assert isinstance(boundary, dict)\n    boundary["scientific_status_changed"] = True\n    _wire(monkeypatch, consumer=consumer, base=_base_report())\n    with pytest.raises(module.ScientificCriticError, match="scientific_status_changed=false"):\n        module.build_authenticated_scientific_critic_report(\n            tmp_path / "bundle", program_state={"generated_goals": []}\n        )\n'''
    TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
