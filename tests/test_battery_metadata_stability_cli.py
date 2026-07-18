import json

from src.cli import main


def test_metadata_stability_preview_is_local_and_bounded(capsys):
    code = main(["--json", "preview-battery-source-metadata-audit"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] in {"ready_for_local_execution", "blocked_missing_local_source"}
    assert payload["sensitivity_policy_count"] == 9
    assert payload["network_called"] is False
    assert payload["automatic_download"] is False
    assert payload["model_or_solver_executed"] is False


def test_metadata_stability_run_requires_explicit_execute(capsys):
    code = main(["--json", "run-battery-metadata-stability-audit"])
    payload = json.loads(capsys.readouterr().out)

    assert code != 0
    assert payload["status"] == "blocked_explicit_execute_required"
    assert payload["network_called"] is False


def test_metadata_stability_show_validate_and_external_decision_commands(capsys):
    code = main(["--json", "show-battery-metadata-stability"])
    shown = json.loads(capsys.readouterr().out)
    assert code == 0
    assert shown["status"] == "available"
    assert shown["decision"]["representative_mechanism"] == "none"

    code = main(["--json", "validate-battery-metadata-stability"])
    validated = json.loads(capsys.readouterr().out)
    assert code == 0
    assert validated["valid"] is True

    code = main(["--json", "evaluate-battery-external-data-requirement"])
    external = json.loads(capsys.readouterr().out)
    assert code == 0
    assert external["status"] == "evaluated"
    assert external["automatic_download_performed"] is False
