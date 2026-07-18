import json

from src.cli import main


def test_inspect_capacity_evaluator_cli_is_metadata_only(capsys):
    code = main(["--json", "inspect-battery-capacity-evaluator"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["evaluator_id"] == "battery_capacity_trajectory_consistency_evaluator_v1"
    assert payload["operator_role"] == "Evaluator"
    assert payload["network_policy"] == "no_network"
    assert payload["target_access_policy"] == "observed_capacity_only_no_predictive_target"


def test_validate_tracked_capacity_result_cli(capsys):
    code = main(
        [
            "--json",
            "validate-battery-capacity-evaluator-result",
            "data/processed/battery_v2_3_4_evaluator_decision.json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["valid"] is True
    assert payload["row_count"] == 1


def test_show_capacity_findings_trust_and_claims_cli(capsys):
    for command, expected_status in (
        (["--json", "show-battery-capacity-findings-summary"], "available"),
        (["--json", "assess-battery-capacity-evaluator-trust"], "assessed"),
        (["--json", "evaluate-battery-capacity-claims"], "evaluated"),
    ):
        code = main(command)
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["status"] == expected_status
