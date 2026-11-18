"""Pinned source, numerical verification, and persistent CLI tests for rod thermal action."""

import copy
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import scipy

from materials_data_analyzer.research_loop import rod_thermal_comparison as comparison
from materials_data_analyzer.research_loop.kernel import (
    ResearchLoopError,
    verify_research_loop,
)
from materials_data_analyzer.research_loop.rod_thermal_contract import (
    ACTION,
    MODEL,
    load_view,
    validate_request,
)
from materials_data_analyzer.research_loop.rod_thermal_profile import run_rod_episode
from materials_data_analyzer.research_loop.rod_thermal_solver import predict
from materials_data_analyzer.research_program_cli import main

ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _put(directory, name, header, data):
    file = directory / name
    np.savetxt(file, data, delimiter=",", header=header, comments="")
    return {"path": name, "sha256": _sha(file)}


@pytest.fixture
def rod(tmp_path):
    src = tmp_path / "input"
    src.mkdir()
    request = {
        "schema_version": "1.0",
        "action_type": ACTION,
        "model_id": MODEL,
        "model_version": "1.0",
        "scipy_version": scipy.__version__,
        "prior_ledger_sha256": None,
        "source_columns": {"time_s": "Time", "boundary": "TC", "s1": "S1", "s2": "S2"},
        "material": {
            "identity": "non-Al synthetic fixture",
            "source": "test only",
            "density": 7000,
            "specific_heat": 500,
            "k_bounds": [30, 150],
            "h_max": 100,
            "units": {
                "density": "kg/m^3",
                "specific_heat": "J/(kg*K)",
                "conductivity": "W/(m*K)",
                "heat_loss": "W/(m^2*K)",
            },
        },
        "geometry": {
            "length": 0.12,
            "diameter": 0.006,
            "length_unit": "m",
            "boundary": "measured_dirichlet_insulated_tip",
            "sensors": [
                {"id": "s1", "position_m": 0.03},
                {"id": "s2", "position_m": 0.075},
            ],
        },
        "temperatures": {
            "encoding": "excess_K",
            "reference_K": 295.0,
            "ambient_K": 295.0,
        },
        "numerics": {
            "grid": 48,
            "grid_tol_K": 0.1,
            "bdf_tol_K": 0.015,
            "duration_s": 30,
            "late_start_s": 20,
        },
    }
    t = np.linspace(0, 30, 101)
    b = 12 * (1 - np.exp(-t / 5))
    spec = {
        "length": 0.12,
        "diameter": 0.006,
        "density": 7000,
        "specific_heat": 500,
        "positions": [0.03, 0.075],
    }
    train = predict(t, b, spec, 75.0, 26.0, 48)
    held = predict(t, b * 1.3, spec, 75.0, 26.0, 48)
    orig_train = _put(src, "original-train.csv", "Time,TC,S1,S2", np.c_[t, b, train])
    orig_held = _put(src, "original-held.csv", "Time,TC,S1,S2", np.c_[t, b * 1.3, held])
    request["partition"] = {
        "calibration": {
            "id": "train",
            "original_path": orig_train["path"],
            "original_sha256": orig_train["sha256"],
            "source": "test train",
            "series": _put(
                src, "train.csv", "time_s,boundary,s1,s2", np.c_[t, b, train]
            ),
        },
        "validation": [
            {
                "id": "held",
                "original_path": orig_held["path"],
                "original_sha256": orig_held["sha256"],
                "source": "test evaluation",
                "driver": _put(src, "driver.csv", "time_s,boundary", np.c_[t, b * 1.3]),
                "response": _put(src, "held.csv", "time_s,s1,s2", np.c_[t, held]),
            }
        ],
    }
    return request, src, tmp_path / "output"


def _run(rod):
    request, src, output = rod
    path = src / "case.json"
    path.write_text(json.dumps(request))
    return run_rod_episode(
        repository_root=ROOT,
        output_root=output,
        request_path=path,
        expected_sha256=_sha(path),
        prior_run=None,
        max_cycles=1,
    )


def test_registered_cli_run_freezes_before_response_replans_and_resumes(
    rod, monkeypatch, capsys
):
    request, src, output = rod
    path = src / "case.json"
    path.write_text(json.dumps(request))
    original = comparison.load_bound_view
    accesses = []

    def check(directory, record, role, header, spec):
        if role != "series":
            staged = list(output.glob("ledger/actions/.*/prediction-freeze.json"))
            assert len(staged) == 1
            freeze = json.loads(staged[0].read_text())
            assert freeze["validation_response_parsed"] is False
            assert (
                _sha(staged[0].with_name("frozen-predictions.json"))
                == freeze["forecast_sha256"]
            )
        accesses.append(record[role]["path"])
        return original(directory, record, role, header, spec)

    monkeypatch.setattr(comparison, "load_bound_view", check)
    args = [
        "run-autonomous",
        "--repository-root",
        str(ROOT),
        "--rod-request",
        str(path),
        "--rod-request-sha256",
        _sha(path),
        "--output",
        str(output),
    ]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["actions_appended_this_invocation"] == 1
    assert accesses == ["train.csv", "driver.csv", "held.csv"]
    assert verify_research_loop(output / "ledger")["valid"]
    actions = output / "ledger" / "actions" / ACTION
    result = json.loads((actions / "comparison.json").read_text())
    assert result["response_access_started_utc"] >= result["freeze"]["timestamp_utc"]
    assert result["runs"]["held"]["models"]["distributed_loss"]["rmse_K"] < 1e-5
    packet = json.loads((actions / "evidence-packet.json").read_text())
    assert packet["authority"]["scientific_status_promoted"] is False
    assert packet["authority"]["empirical_evidence_created"] is False
    step = first["planning_record"]
    assert (
        step["before"]["plan"]["selected_next_action"]["description"]
        != step["after"]["plan"]["selected_next_action"]["description"]
    )

    assert main(args) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["actions_appended_this_invocation"] == 0
    assert resumed["ledger_sha256"] == first["ledger_sha256"]
    assert len(accesses) == 3
    with (actions / "comparison.json").open("ab") as f:
        f.write(b" ")
    assert main(args) == 1
    assert "checksum mismatch" in capsys.readouterr().err


@pytest.mark.parametrize(
    "case", ["id", "original", "unit", "definition", "position", "bound", "approval"]
)
def test_request_fails_closed(rod, case):
    request, _, _ = rod
    held = request["partition"]["validation"][0]
    if case == "id":
        held["id"] = "TRAIN"
    elif case == "original":
        held["original_sha256"] = request["partition"]["calibration"]["original_sha256"]
    elif case == "unit":
        request["material"]["units"]["conductivity"] = "W"
    elif case == "definition":
        request["temperatures"]["encoding"] = "absolute_K"
    elif case == "position":
        request["geometry"]["sensors"].reverse()
    elif case == "bound":
        request["material"]["k_bounds"] = [0, 5000]
    else:
        request["scientific_status_upgrade_authorized"] = True
    with pytest.raises(ResearchLoopError):
        _run(rod)


@pytest.mark.parametrize("case", ["time", "order", "sha", "leakage"])
def test_view_rejects_named_input_failures(rod, case):
    request, src, _ = rod
    held = request["partition"]["validation"][0]
    ref = copy.deepcopy(held["driver"])
    path = src / ref["path"]
    if case == "time":
        rows = path.read_text().splitlines()
        rows[1], rows[2] = rows[2], rows[1]
        path.write_text("\n".join(rows) + "\n")
    elif case == "order":
        path.write_text(path.read_text().replace("time_s,boundary", "boundary,time_s"))
    elif case == "leakage":
        path.write_text("time_s,boundary,s1\n0,0,0\n1,0,0\n30,1,1\n")
    else:
        path.write_text(path.read_text() + "\n")
    if case != "sha":
        ref["sha256"] = _sha(path)
    with pytest.raises(ResearchLoopError):
        load_view(src, ref, ["time_s", "boundary"], validate_request(request))


def test_convergence_failure_archived_without_opening_validation(rod):
    request, _, output = rod
    request["numerics"]["grid_tol_K"] = 1e-10
    outcome = _run(rod)
    assert outcome["action_report"]["execution_status"] == "failed"
    assert "numerical tolerance" in outcome["action_report"]["diagnostic"]
    assert not list(output.rglob("prediction-freeze.json"))
    assert verify_research_loop(output / "ledger")["valid"]
    assert _run(rod)["actions_appended_this_invocation"] == 0


def test_historical_al_predictions_when_local_frozen_artifacts_supplied():
    name = os.environ.get("MDA_ROD_HISTORICAL_ARTIFACTS")
    if name is None:
        pytest.skip(
            "Local archived Al6061 research artifacts are not bundled with the repository"
        )
    root = Path(name)
    old = json.loads((root / "EVALUATION.json").read_text())
    action = root / "typed-action-followup/final-al/ledger/actions" / ACTION
    result = json.loads((action / "comparison.json").read_text())
    frozen = json.loads((action / "frozen-predictions.json").read_text())
    for run, metrics in old.items():
        reference = np.loadtxt(root / f"PRED_{run}.csv", delimiter=",", skiprows=1)
        for model, original, start in (
            ("conduction", "H0", 2),
            ("distributed_loss", "H1", 7),
        ):
            assert result["runs"][run]["models"][model]["rmse_K"] == pytest.approx(
                metrics["models"][original]["rmse_K"], abs=1e-5
            )
            assert (
                np.max(
                    abs(
                        np.asarray(frozen[run]["models"][model]["values_K"])
                        - reference[:, start : start + 5]
                    )
                )
                < 1e-5
            )


def test_recover_published_action_without_second_fit(rod, monkeypatch):
    from materials_data_analyzer.research_loop import rod_thermal_action

    def interrupt(*args, **kwargs):
        raise InterruptedError("between output publication and ledger commit")

    with monkeypatch.context() as patch:
        patch.setattr(rod_thermal_action, "append_action", interrupt)
        with pytest.raises(InterruptedError):
            _run(rod)
    _, _, output = rod
    action = output / "ledger" / "actions" / ACTION
    before = _sha(action / "frozen-predictions.json")

    def prohibit_compute(*args, **kwargs):
        pytest.fail("Published calculation must not be repeated")

    monkeypatch.setattr(rod_thermal_action, "compare", prohibit_compute)
    recovered = _run(rod)
    assert recovered["action_report"]["execution_status"] == "completed"
    assert recovered["actions_appended_this_invocation"] == 1
    assert _sha(action / "frozen-predictions.json") == before
    assert verify_research_loop(output / "ledger")["valid"]
    assert _run(rod)["actions_appended_this_invocation"] == 0


@pytest.mark.parametrize("case", ["raw_mutation", "relabeled_response_as_driver"])
def test_original_authentication_rejects_mutated_or_falsely_projected_acquisition(
    rod, case
):
    request, src, _ = rod
    validation = request["partition"]["validation"][0]
    if case == "raw_mutation":
        with (src / validation["original_path"]).open("ab") as handle:
            handle.write(b"\n")
    else:
        driver = np.loadtxt(
            src / validation["response"]["path"], delimiter=",", skiprows=1
        )
        validation["driver"] = _put(
            src, "counterfeit.csv", "time_s,boundary", driver[:, :2]
        )
    result = _run(rod)
    assert result["action_report"]["execution_status"] == "failed"
    assert (
        "Original acquisition SHA-256 mismatch"
        if case == "raw_mutation"
        else "differs from the authenticated original channels"
    ) in result["action_report"]["diagnostic"]


@pytest.mark.parametrize("eligible", [False, True])
def test_opt_in_followup_depends_on_comparison(rod, monkeypatch, eligible):
    from materials_data_analyzer.research_loop import (
        rod_thermal_identifiability as diagnostic,
    )

    request, src, output = rod
    path = src / "case.json"
    path.write_text(json.dumps(request))
    original = comparison.calibrate

    def calibrate(*args):
        fitted = original(*args)
        fitted["distributed_loss"]["k_h_sensitivity_cosine"] = (
            -0.99 if eligible else -0.5
        )
        return fitted

    monkeypatch.setattr(comparison, "calibrate", calibrate)
    access = []
    load = diagnostic.load_bound_view

    def checked(directory, run, role, header, spec):
        access.append(role)
        return load(directory, run, role, header, spec)

    monkeypatch.setattr(diagnostic, "load_bound_view", checked)
    options = {
        "repository_root": ROOT,
        "output_root": output,
        "request_path": path,
        "expected_sha256": _sha(path),
        "prior_run": None,
        "max_cycles": 2,
        "authorize_identifiability": True,
    }
    first = run_rod_episode(**options)
    assert first["actions_appended_this_invocation"] == 1 + int(eligible)
    if not eligible:
        assert first["episode"]["conclusion"]["reason"] == "no_qualified_followup"
        assert not access
        return

    assert access == ["series"]
    assert first["identifiability_action_report"]["empirical_evidence_created"] is False
    result = output / "ledger" / "actions" / diagnostic.ACTION / diagnostic.RESULT
    data = json.loads(result.read_bytes())
    assert first["episode"]["conclusion"]["reason"] == data["decision"]
    assert data["evaluation_response_accessed"] is False
    assert data["full"]["log_parameter_rms_singular_values_K"][0] > 0
    assert max(row["bdf_relative_l2_error"] for row in data["verification"]) < 0.05
    assert verify_research_loop(output / "ledger")["valid"]
    resumed = run_rod_episode(**options)
    assert resumed["actions_appended_this_invocation"] == 0
    assert resumed["ledger_sha256"] == first["ledger_sha256"]
    result.write_bytes(result.read_bytes() + b" ")
    with pytest.raises(ResearchLoopError, match="checksum mismatch"):
        run_rod_episode(**options)


def test_followup_recovers_after_output_before_ledger(rod, monkeypatch):
    from materials_data_analyzer.research_loop import rod_thermal_action as executor
    from materials_data_analyzer.research_loop import (
        rod_thermal_identifiability as diagnostic,
    )

    request, src, output = rod
    path = src / "case.json"
    path.write_text(json.dumps(request))
    calibrate = comparison.calibrate

    def eligible(*args):
        fit = calibrate(*args)
        fit["distributed_loss"]["k_h_sensitivity_cosine"] = -0.99
        return fit

    monkeypatch.setattr(comparison, "calibrate", eligible)
    append = executor.append_action

    def crash(*args, **kwargs):
        if kwargs["action_id"] == diagnostic.ACTION:
            raise RuntimeError("crash before diagnostic ledger commit")
        return append(*args, **kwargs)

    monkeypatch.setattr(executor, "append_action", crash)
    options = {
        "repository_root": ROOT,
        "output_root": output,
        "request_path": path,
        "expected_sha256": _sha(path),
        "prior_run": None,
        "max_cycles": 2,
        "authorize_identifiability": True,
    }
    with pytest.raises(RuntimeError, match="crash before"):
        run_rod_episode(**options)
    artifact = output / "ledger" / "actions" / diagnostic.ACTION / diagnostic.RESULT
    sha = _sha(artifact)
    monkeypatch.setattr(executor, "append_action", append)

    def never_execute(*_args):
        pytest.fail("already-published diagnostic ran again")

    monkeypatch.setattr(diagnostic, "diagnose", never_execute)
    result = run_rod_episode(**options)
    assert result["actions_appended_this_invocation"] == 1
    assert result["identifiability_action_report"]["execution_status"] == "completed"
    assert _sha(artifact) == sha
    assert run_rod_episode(**options)["actions_appended_this_invocation"] == 0


def test_followup_flag_cannot_enter_in625(capsys):
    assert main(["run-autonomous", "--rod-identifiability"]) == 1
    assert "Rod pins require --rod-request" in capsys.readouterr().err
