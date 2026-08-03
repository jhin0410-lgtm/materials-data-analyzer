# Testing

Run the complete repository test suite from the project root:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

On Windows, the repository-local runner can isolate pytest temporary files:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

## Automated validation layers

The standard CI workflow validates Python 3.11 on Ubuntu and Windows, builds a wheel and source distribution, installs the wheel without dependency resolution, and exercises the installed public CLIs.

The quality workflow adds:

- a coverage gate with a retained XML report;
- full-suite compatibility runs on Python 3.12 and 3.13;
- a clean source-distribution self-test using only files packaged in the sdist;
- Ruff static checks;
- focused mypy validation for stable safety and semantic-contract modules;
- dependency vulnerability auditing;
- a retained exact environment freeze.

The supported runtime range is Python 3.11 through 3.13. A future Python version is not supported merely because installation happens to succeed.

## Scientific interpretation

Passing tests establishes software behavior only. It does not establish that samples are comparable, units and measurement methods are correct, an SPC process is stable, a model generalizes, a mechanism is causal, or an engineering decision is authorized.

Synthetic and compact fixtures test software contracts. They are not substitutes for independent real-data scientific validation.

## Generated artifacts

Tests and smoke commands may write under `outputs/`. That directory is ignored by Git. User-facing runs now stage outputs in a sibling temporary directory and promote them only after successful completion. Existing recognized runs are preserved until replacement succeeds, and foreign non-empty directories are not recursively deleted.
