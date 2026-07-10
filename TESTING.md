# Testing

Run the test suite from the project root:

```bash
python -m pytest -q
```

On Windows, if the default user temp directory causes `tmp_path` or permission errors, use the repository-local test runner:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1 tests/test_battery_archive_connector.py -q
```

The runner creates a unique pytest temp directory under `outputs/pytest-temp`, sets `TEMP` and `TMP` only for that PowerShell process, forwards any extra arguments to `python -m pytest`, and removes its own temp directory after the run. `outputs/` is ignored by Git, so these temporary test artifacts are not committed.

GitHub Actions also runs `pytest -q` on push and pull request events using the workflow in `.github/workflows/ci.yml`.

The tests use small in-memory pandas DataFrames and demo/synthetic CSV files from `data/sample/`. They do not use real experimental, factory, customer, or production data.

## What The Tests Cover

- CSV loading and input validation behavior
- column cleanup and duplicate-column detection
- missing-value summaries, numeric summaries, correlations, and group summaries
- process scoring, multi-objective scoring, SPC calculations, and simulation helper behavior
- a lightweight CLI regression check using the included demo dataset

## What The Tests Do Not Cover

- validation of real engineering conclusions
- production-scale datasets
- private or proprietary data handling
- full visual inspection of every generated figure
- package installation as an installed Python module

Some tests and demo commands create files under `outputs/`. The `outputs/` directory is ignored by Git, so local run artifacts and test artifacts should not be committed.
