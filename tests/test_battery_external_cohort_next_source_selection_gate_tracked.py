from __future__ import annotations

import json
from pathlib import Path
import shutil

from src.platform_core import battery_external_cohort_next_source_selection_gate as mod


def test_tracked_summary_matches_generator_byte_for_byte(tmp_path: Path):
    for relative in (
        mod.DEFAULT_CONFIG_PATH,
        mod.DEFAULT_CONTRACT_PATH,
        mod.DEFAULT_REGISTER_PATH,
        mod.DEFAULT_V264_PATH,
        mod.DEFAULT_V2610_PATH,
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    config = mod.load_config(repo_root=tmp_path)
    result = mod.execute(config, repo_root=tmp_path, write_outputs=False)
    generated = mod.compact(result)
    expected = (
        json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    tracked = Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    assert generated["deterministic_result_checksum"] == (
        "5cbb6b979bd6529e28d24af1ecb0e1579439fef2be710904081d8e81d032747b"
    )
    mod.validate_result(generated)
