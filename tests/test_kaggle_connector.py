"""Tests for Kaggle connector behavior without real API calls."""

from __future__ import annotations

import builtins

import pytest

from connectors.kaggle_connector import KaggleConnector, safe_dataset_name


def test_safe_dataset_name_replaces_path_separator() -> None:
    assert (
        safe_dataset_name("patrickfleith/nasa-battery-dataset")
        == "patrickfleith_nasa-battery-dataset"
    )


def test_kaggle_missing_package_raises_friendly_runtime_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("kaggle"):
            raise ModuleNotFoundError("No module named 'kaggle'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="kaggle package"):
        KaggleConnector("owner/dataset").fetch(limit=1)


def test_kaggle_requires_dataset_slug() -> None:
    with pytest.raises(ValueError, match="dataset slug"):
        KaggleConnector("").fetch(limit=1)
