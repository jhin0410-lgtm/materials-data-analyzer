from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer.research_loop_cli import main


ROOT = Path(__file__).resolve().parents[1]


def _copy_tracked(tmp_path: Path, relative: str) -> None:
    source = ROOT / relative
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def test_plan_next_action_cli_supports_tm_fe_si_stop(
    tmp_path: Path,
    capsys,
) -> None:
    _copy_tracked(
        tmp_path,
        "configs/research/tm_fe_si_characterization_consumer_readiness.v1.json",
    )

    exit_code = main(
        [
            "plan-next-action",
            "--adapter",
            "tm-fe-si-descriptive",
            "--repository-root",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["adapter_id"] == "tm-fe-si-descriptive"
    assert payload["selection_status"] == "no_positive_value_action"
    assert payload["maximum_allowed_use"] == "descriptive"
    assert captured.err == ""
