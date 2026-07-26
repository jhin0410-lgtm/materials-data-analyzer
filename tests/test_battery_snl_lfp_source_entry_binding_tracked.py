from __future__ import annotations

import json
from pathlib import Path

from src.platform_core import battery_snl_lfp_source_entry_binding as mod


def test_tracked_summary_matches_current_generator_byte_for_byte():
    config = mod.load_config()
    manifest = json.loads(Path(config.manifest_path).read_text(encoding="utf-8"))
    v265 = json.loads(Path(config.v2_6_5_summary_path).read_text(encoding="utf-8"))
    v266 = json.loads(Path(config.v2_6_6_summary_path).read_text(encoding="utf-8"))

    generated = mod.compact(mod.build_result(config, manifest, v265, v266))
    expected_text = json.dumps(
        generated,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"
    tracked_path = Path(config.tracked_summary_path)

    assert tracked_path.read_text(encoding="utf-8") == expected_text
    mod.validate_result(generated)
