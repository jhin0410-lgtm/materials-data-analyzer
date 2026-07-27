# Contributing

Thank you for considering a contribution to `materials-data-analyzer`.

This project prioritizes scientific validity, provenance, reproducibility, and conservative claim boundaries. Contributions should preserve those priorities as well as existing public CLI behavior unless a breaking change is explicitly justified and documented.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
```

On Windows, the repository-local test runner can also be used:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

## Contribution scope

Keep changes focused. Do not combine a feature or bug fix with unrelated refactoring, dependency upgrades, generated artifacts, or data acquisition.

Before opening a pull request:

- add or update tests for changed behavior;
- preserve public CLI arguments, output schemas, filenames, and valid workflows unless the change is intentionally breaking;
- document assumptions, units, preprocessing, exclusions, and scientific limitations;
- distinguish software validation from scientific validation;
- avoid causal, mechanistic, production-readiness, or generalization claims that the evidence does not support;
- update relevant documentation and examples;
- run the relevant test suite.

## Data and artifact policy

Do not commit:

- API keys, tokens, passwords, private keys, or credential files;
- unpublished, proprietary, institution-owned, customer, personal, or otherwise confidential data;
- raw downloaded datasets unless their redistribution terms explicitly permit it and inclusion is necessary;
- large row-level predictions, local registries, caches, generated reports, or other regenerable outputs.

Synthetic sample data and compact, source-documented summary artifacts may be committed when they are necessary for tests, examples, or reproducibility. Every externally sourced dataset must include its source, license or access terms, retrieval context, preprocessing method, and known limitations.

## Pull requests

Use a clear title and explain:

1. what changed;
2. why it changed;
3. files and public behavior affected;
4. tests and commands run;
5. scientific assumptions and limitations;
6. generated artifacts intentionally included or excluded.

A passing test suite confirms software behavior only. It does not by itself validate a scientific method, dataset comparison, physical interpretation, or engineering recommendation.
