# Contributing

Thank you for helping improve `materials-data-analyzer`.

## Before Starting

- Check the current `README.md`, relevant case-study documentation, and tests.
- Keep the change focused on a defined user or scientific need.
- Do not redesign public interfaces, output schemas, or repository structure
  unless the change requires it and the migration is documented.
- Prefer a small complete workflow over a broad unfinished framework.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

On Windows, the repository-local test runner may also be used:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

## Contribution Requirements

A pull request should include:

- a clear objective and scope;
- implementation and proportional tests;
- a user-facing command or example when behavior changes;
- preserved public CLI and output behavior unless a breaking change is explicit;
- documentation of assumptions, units, preprocessing, exclusions, and
  scientific limitations where relevant;
- a concise completion report with files changed and test results.

## Scientific and Data Requirements

Treat every row, image, spectrum, and trajectory as a physical measurement with
context. Do not invent missing sample identity, units, processing history,
measurement conditions, calibration, uncertainty, or provenance.

Do not silently:

- change units;
- remove records or outliers;
- interpolate trajectories;
- smooth spectra or alter images;
- average duplicate measurements;
- combine datasets by row order or inferred filenames;
- promote synthetic tests into real-world scientific evidence.

Separate software validation from scientific validation. Passing tests proves
that the implementation behaves as specified; it does not prove that a method,
model, or scientific claim is valid for real measurements.

## Files That Must Not Be Committed

Do not commit:

- API keys, tokens, passwords, private keys, or local secret files;
- proprietary, personal, export-controlled, or employer-confidential data;
- raw downloaded datasets unless redistribution is explicitly permitted and the
  repository has intentionally approved tracking them;
- generated `outputs/`, caches, local databases, or row-level predictions;
- absolute local filesystem paths.

External datasets remain subject to their upstream terms. See
[`NOTICE.md`](NOTICE.md).

## Pull Requests

Use a feature branch and keep unrelated refactoring out of the pull request.
Before requesting review:

```powershell
git status --short
python -m pytest -q
```

Report test failures and limitations honestly. Do not weaken tests, scientific
boundaries, or provenance checks merely to make CI pass.
