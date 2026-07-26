from __future__ import annotations

import json
from pathlib import Path
import shutil

from src.platform_core import (
    battery_michigan_formation_provider_package_structure_gate as mod,
)


def test_tracked_summary_matches_generator_byte_for_byte(tmp_path: Path):
    for relative in (
        mod.DEFAULT_CONFIG_PATH,
        mod.DEFAULT_CONTRACT_PATH,
        mod.DEFAULT_EVIDENCE_PATH,
        mod.DEFAULT_V2611_PATH,
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    config = mod.load_config(repo_root=tmp_path)
    generated = mod.execute(config, repo_root=tmp_path, write_outputs=False)
    expected = (
        json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    tracked = Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    assert generated["deterministic_result_checksum"] == (
        "b1ce09e4ce06c9ec90839b63e1f2546d1fd2808f9c8ea6717edc5bc0fe93ce7d"
    )
    mod.validate_result(generated)
