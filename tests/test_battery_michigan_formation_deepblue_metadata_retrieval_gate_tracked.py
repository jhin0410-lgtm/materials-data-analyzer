from __future__ import annotations

import json
from pathlib import Path
import shutil

from src.platform_core import battery_michigan_formation_deepblue_metadata_access_closeout as closeout
from src.platform_core import battery_michigan_formation_deepblue_metadata_retrieval_gate as gate


def test_tracked_access_denial_summary_matches_closeout_byte_for_byte(tmp_path: Path):
    for relative in (
        gate.DEFAULT_CONFIG_PATH,
        gate.DEFAULT_CONTRACT_PATH,
        gate.DEFAULT_EVIDENCE_PATH,
        gate.DEFAULT_V2612_PATH,
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    generated = closeout.execute(repo_root=tmp_path, write_outputs=False)
    expected = json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tracked = Path(gate.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    assert generated["retrieval_status"] == "failed"
    assert generated["error_category"] == "http_status_403"
    assert generated["network_called"] is True
    assert generated["network_call_count"] == 1
    assert generated["deterministic_result_checksum"] == closeout.EXPECTED_FAILURE_CHECKSUM
    closeout.validate_result(generated)
