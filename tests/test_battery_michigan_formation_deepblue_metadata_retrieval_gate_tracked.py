from __future__ import annotations

import json
from pathlib import Path
import shutil

from src.platform_core import battery_michigan_formation_deepblue_metadata_retrieval_gate as mod


def test_tracked_pending_summary_matches_preview_byte_for_byte(tmp_path: Path):
    for relative in (
        mod.DEFAULT_CONFIG_PATH,
        mod.DEFAULT_CONTRACT_PATH,
        mod.DEFAULT_EVIDENCE_PATH,
        mod.DEFAULT_V2612_PATH,
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    config = mod.load_config(repo_root=tmp_path)
    generated = mod.execute(config, repo_root=tmp_path, run_network=False)
    expected = json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tracked = Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    assert generated["deterministic_result_checksum"] == "ea35e4a5dbd7e1233750aac795d6b112750e0f0de9a564467c1cfea660a16eef"
    mod.validate_result(generated)
