from pathlib import Path

from src.platform_core.side_effects import create_side_effect_snapshot, evaluate_side_effects


def test_side_effect_guard_allows_only_output_directory(tmp_path):
    protected = tmp_path / "data" / "processed" / "input.csv"
    protected.parent.mkdir(parents=True)
    protected.write_text("a\n1\n", encoding="utf-8")
    output = tmp_path / "outputs" / "platform_runs" / "demo"
    snapshot = create_side_effect_snapshot(tmp_path, {"input": protected}, output)
    output.mkdir(parents=True)
    (output / "report.json").write_text("{}\n", encoding="utf-8")

    report = evaluate_side_effects(
        tmp_path,
        snapshot,
        {"input": protected},
        output,
        max_output_files=2,
        max_output_bytes=100,
    )

    assert report.status == "allowed_outputs_only"
    assert report.unexpected_files == ()
    assert report.protected_changes == ()


def test_side_effect_guard_detects_protected_change_and_unexpected_file(tmp_path):
    protected = tmp_path / "data" / "processed" / "input.csv"
    protected.parent.mkdir(parents=True)
    protected.write_text("a\n1\n", encoding="utf-8")
    output = tmp_path / "outputs" / "platform_runs" / "demo"
    snapshot = create_side_effect_snapshot(tmp_path, {"input": protected}, output)
    protected.write_text("a\n2\n", encoding="utf-8")
    (tmp_path / "unexpected.txt").write_text("bad\n", encoding="utf-8")

    report = evaluate_side_effects(
        tmp_path,
        snapshot,
        {"input": protected},
        output,
        max_output_files=2,
        max_output_bytes=100,
    )

    assert report.status == "prohibited_modification"
    assert report.protected_changes == ("input",)
    assert report.unexpected_files == ("unexpected.txt",)


def test_side_effect_guard_enforces_output_limits(tmp_path):
    protected = tmp_path / "data" / "processed" / "input.csv"
    protected.parent.mkdir(parents=True)
    protected.write_text("a\n1\n", encoding="utf-8")
    output = tmp_path / "outputs" / "platform_runs" / "demo"
    snapshot = create_side_effect_snapshot(tmp_path, {"input": protected}, output)
    output.mkdir(parents=True)
    (output / "one.txt").write_text("12345", encoding="utf-8")

    report = evaluate_side_effects(
        tmp_path,
        snapshot,
        {"input": protected},
        output,
        max_output_files=1,
        max_output_bytes=3,
    )

    assert report.status == "output_limit_exceeded"
