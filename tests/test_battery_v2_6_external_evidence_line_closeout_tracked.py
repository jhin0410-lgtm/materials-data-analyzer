from __future__ import annotations

import json
from pathlib import Path

from src.platform_core import battery_v2_6_external_evidence_line_closeout as mod


def test_tracked_closeout_matches_regeneration_byte_for_byte():
    generated = mod.execute(mod.load_config())
    expected = json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tracked = Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    assert generated["deterministic_result_checksum"] == mod.EXPECTED_RESULT_CHECKSUM
    mod.validate_result(generated)
