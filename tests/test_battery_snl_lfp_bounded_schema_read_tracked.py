from __future__ import annotations

import json
from pathlib import Path
import shutil

from src.platform_core import battery_snl_lfp_bounded_schema_read as mod


def test_tracked_pending_summary_matches_generator_byte_for_byte(tmp_path: Path):
    for relative in (
        mod.DEFAULT_CONFIG_PATH,
        mod.DEFAULT_CONTRACT_PATH,
        "data/processed/battery_v2_6_7_snl_lfp_source_entry_binding_summary.json",
        "data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json",
    ):
        source = Path(relative)
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    config = mod.load_config(repo_root=tmp_path)
    contract = json.loads((tmp_path / config.contract_path).read_text(encoding="utf-8"))
    v267 = json.loads((tmp_path / config.v2_6_7_summary_path).read_text(encoding="utf-8"))
    v266 = json.loads((tmp_path / config.v2_6_6_summary_path).read_text(encoding="utf-8"))
    generated = mod.compact(mod.build_result(config, contract, v267, v266, tmp_path))
    expected = json.dumps(generated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    tracked = Path(mod.DEFAULT_TRACKED_SUMMARY).read_text(encoding="utf-8")
    assert tracked == expected
    mod.validate_result(generated)


def test_v2_6_8_json_artifacts_parse():
    for path in (
        Path("data/platform/battery_bounded_schema_read_config_schema_v1.json"),
        Path("data/platform/battery_bounded_schema_read_contract_schema_v1.json"),
        Path("data/platform/battery_bounded_schema_read_result_schema_v1.json"),
        Path(mod.DEFAULT_CONTRACT_PATH),
        Path(mod.DEFAULT_TRACKED_SUMMARY),
    ):
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
