from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/scientific_critic_authenticated_policy.py")
TESTS = Path("tests/test_scientific_critic_authenticated_policy.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    marker = "\ndef build_authenticated_scientific_critic_report(\n"
    if source.count(marker) != 1:
        raise SystemExit(f"validator insertion anchor count={source.count(marker)}")
    helper = r'''

def _validate_consumer_authority_boundary(consumer: Mapping[str, Any]) -> None:
    if consumer.get("current_transition_exact_provenance_authenticated") is not True:
        raise ScientificCriticError(
            "authenticated critic adapter requires independently authenticated current-transition provenance"
        )
    boundary = consumer.get("authority_boundary")
    if not isinstance(boundary, Mapping):
        raise ScientificCriticError("authenticated transition consumer authority boundary is malformed")
    forbidden_true = (
        "scientific_authority_applied",
        "execution_authorized",
        "positive_closeout_granted",
        "verifier_identity_or_credential_authenticated",
        "support_independence_established",
        "empirical_origin_independently_established",
    )
    for field in forbidden_true:
        if boundary.get(field) is not False:
            raise ScientificCriticError(
                f"authenticated transition consumer must explicitly keep {field}=false"
            )
    if consumer.get("inference_scope") == "empirical_derived":
        raise ScientificCriticError(
            "empirical_derived critic authority remains disabled until the evidence-origin contract is authenticated"
        )
'''
    source = source.replace(marker, helper + marker, 1)
    source = replace_once(
        source,
        '''    consumer = authenticate_transition_bundle(root)
    graph_path = root / "epistemic_graph.json"
''',
        '''    consumer = authenticate_transition_bundle(root)
    _validate_consumer_authority_boundary(consumer)
    graph_path = root / "epistemic_graph.json"
''',
        "consumer-boundary-call",
    )
    SOURCE.write_text(source, encoding="utf-8")

    tests = TESTS.read_text(encoding="utf-8")
    tests = replace_once(
        tests,
        '''        "authority_boundary": {
            "scientific_authority_applied": False,
            "execution_authorized": False,
            "positive_closeout_granted": False,
        },
''',
        '''        "authority_boundary": {
            "scientific_authority_applied": False,
            "execution_authorized": False,
            "positive_closeout_granted": False,
            "verifier_identity_or_credential_authenticated": False,
            "support_independence_established": False,
            "empirical_origin_independently_established": False,
        },
''',
        "consumer-test-boundary",
    )
    tests += r'''


def test_adapter_rejects_empirical_derived_even_if_consumer_regresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(
        monkeypatch,
        consumer=_consumer(relation="supports", scope="empirical_derived"),
        base=_base_report(),
    )
    with pytest.raises(
        module.ScientificCriticError,
        match="evidence-origin contract",
    ):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )


def test_adapter_rejects_consumer_authority_escalation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = _consumer(relation="supports")
    boundary = consumer["authority_boundary"]
    assert isinstance(boundary, dict)
    boundary["scientific_authority_applied"] = True
    _wire(monkeypatch, consumer=consumer, base=_base_report())
    with pytest.raises(
        module.ScientificCriticError,
        match="scientific_authority_applied=false",
    ):
        module.build_authenticated_scientific_critic_report(
            tmp_path / "bundle", program_state={"generated_goals": []}
        )
'''
    TESTS.write_text(tests, encoding="utf-8")


if __name__ == "__main__":
    main()
