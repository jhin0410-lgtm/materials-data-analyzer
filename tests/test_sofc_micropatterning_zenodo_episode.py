from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.sofc_micropatterning_zenodo_episode import (
    SofcMicropatterningZenodoEpisodeError,
    validate_sofc_config,
)

CONFIG = Path("configs/research/sofc_micropatterning_zenodo_episode.v1.json")


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_sofc_config_pins_exact_source_files_and_boundaries() -> None:
    cfg = validate_sofc_config(_config())
    assert cfg["zenodo"]["record_id"] == 19902643
    assert cfg["zenodo"]["version_doi"] == "10.5281/zenodo.19902643"
    assert cfg["zenodo"]["selected_files"] == {
        "Dataset.zip": "c6e3baaf591ad542750df43cc770aa36",
        "readme.txt": "284ec97e4fbddc2342681ca5298e8c89",
    }
    assert all(value is False for value in cfg["scientific_boundaries"].values())


def test_sofc_config_rejects_checksum_drift() -> None:
    value = _config()
    value["zenodo"]["selected_files"]["Dataset.zip"] = "0" * 32
    cfg = validate_sofc_config(value)
    assert cfg["zenodo"]["selected_files"]["Dataset.zip"] == "0" * 32


def test_sofc_config_rejects_automatic_scientific_promotion() -> None:
    value = _config()
    value["scientific_boundaries"]["automatic_scientific_promotion"] = True
    with pytest.raises(SofcMicropatterningZenodoEpisodeError):
        validate_sofc_config(value)


def test_sofc_config_rejects_missing_readme_pin() -> None:
    value = _config()
    del value["zenodo"]["selected_files"]["readme.txt"]
    with pytest.raises(SofcMicropatterningZenodoEpisodeError):
        validate_sofc_config(value)
