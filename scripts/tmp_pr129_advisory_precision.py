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
        '''    target["stop_recommendation"] = {\n        "recommendation": recommendation,\n        "rationale": (\n            "Exact current-transition negative directional provenance is independently authenticated. "\n            "The recommendation is advisory/manual only and does not mutate evaluator status."\n        ),\n        "automatic_stop_authorized": False,\n        "positive_scientific_closeout_granted": False,\n    }\n''',
        '''    target["authenticated_stop_advisory"] = {\n        "recommendation": recommendation,\n        "rationale": (\n            "Exact current-transition negative directional provenance is independently authenticated. "\n            "This is a separate advisory and does not replace the base critic stop recommendation."\n        ),\n        "base_critic_stop_recommendation_preserved": True,\n        "automatic_stop_authorized": False,\n        "positive_scientific_closeout_granted": False,\n    }\n''',
        "separate-stop-advisory",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    assert target["stop_recommendation"]["recommendation"] == (\n        "reassess_or_narrow_authenticated_contradicted_scope"\n    )\n    assert target["stop_recommendation"]["automatic_stop_authorized"] is False\n    assert target["stop_recommendation"]["positive_scientific_closeout_granted"] is False\n''',
        '''    assert target["stop_recommendation"]["recommendation"] == "continue_bounded_research"\n    advisory_stop = target["authenticated_stop_advisory"]\n    assert advisory_stop["recommendation"] == (\n        "reassess_or_narrow_authenticated_contradicted_scope"\n    )\n    assert advisory_stop["base_critic_stop_recommendation_preserved"] is True\n    assert advisory_stop["automatic_stop_authorized"] is False\n    assert advisory_stop["positive_scientific_closeout_granted"] is False\n''',
        "contradiction-stop-test",
    )
    text = replace_once(
        text,
        '''    assert target["stop_recommendation"]["recommendation"] == (\n        "reframe_or_narrow_authenticated_falsified_scope"\n    )\n    action = next(\n''',
        '''    assert target["stop_recommendation"]["recommendation"] == "continue_bounded_research"\n    assert target["authenticated_stop_advisory"]["recommendation"] == (\n        "reframe_or_narrow_authenticated_falsified_scope"\n    )\n    action = next(\n''',
        "falsification-stop-test",
    )
    text += '''\n\ndef test_authenticated_advisory_never_downgrades_existing_base_stop_recommendation(\n    tmp_path: Path, monkeypatch: pytest.MonkeyPatch\n) -> None:\n    base = _base_report()\n    target = base["target_reports"][0]\n    target["stop_recommendation"] = {\n        "recommendation": "stop_and_reframe_current_target",\n        "rationale": "Existing verified falsification elsewhere in the graph.",\n        "automatic_stop_authorized": False,\n        "positive_scientific_closeout_granted": False,\n    }\n    _wire(\n        monkeypatch,\n        consumer=_consumer(relation="contradicts"),\n        base=base,\n    )\n    result = module.build_authenticated_scientific_critic_report(\n        tmp_path / "bundle", program_state={"generated_goals": []}\n    )\n    target_result = result["target_reports"][0]\n    assert target_result["stop_recommendation"] == target["stop_recommendation"]\n    assert target_result["authenticated_stop_advisory"]["recommendation"] == (\n        "reassess_or_narrow_authenticated_contradicted_scope"\n    )\n'''
    TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
