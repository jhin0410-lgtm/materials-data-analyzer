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
        "fb53069a149a9cb32dd837f5ef656673c2478072134747e5ed1b4ea997ff617b"
    )
    mod.validate_result(generated)
