from pathlib import Path


def test_config_ignore_policy_keeps_examples_trackable_and_secrets_ignored():
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "configs/*.local.yaml" in text
    assert "configs/local/" in text
    assert "configs/private/" in text
    assert "configs/secrets/" in text
    assert "configs/*.local.json" in text
    assert "configs/*.secret.json" in text
    assert "configs/**" not in text


def test_data_sources_example_contains_no_literal_secret():
    text = Path("configs/data_sources.example.yaml").read_text(encoding="utf-8").lower()

    assert "do not commit" in text
    assert "password=" not in text
    assert "secret=" not in text
    assert "token=" not in text
