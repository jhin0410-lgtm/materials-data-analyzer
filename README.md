# Materials Data Analyzer

[![CI](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/workflows/ci.yml)

`materials-data-analyzer` is a Python-based analysis helper for engineering datasets stored as CSV files. It is aimed at materials experiments, process-condition tables, reliability records, and battery/OLED-style performance datasets where rows represent samples, process runs, or time-series measurements.

This project is not an automatic engineering decision system. It helps organize and summarize data through missing-value checks, descriptive statistics, groupby summaries, correlation analysis, visualization, and Markdown reports. Engineering interpretation still depends on the data source, test conditions, measurement method, and domain review.

## Project Overview

The project provides a CLI workflow around CSV files:

- load and clean tabular experiment/process data,
- standardize column names,
- summarize missing values and numeric columns,
- calculate simple condition-based summaries,
- rank observed rows by selected target columns,
- generate charts and Markdown reports under `outputs/`.

It is intentionally separate from `materials-characterization-analyzer`. XRD, SEM, and EDS workflows belong to that other project; this repository focuses on general CSV-based experiment, process, reliability, and quality data.

## Motivation

Materials and process data often begin as spreadsheets: sample IDs, materials, temperatures, pressures, thicknesses, resistivity, hardness, yield, cycle counts, defect rates, or sensor readings. Before any serious engineering interpretation, the data usually needs a repeatable first pass:

- Are there missing values?
- Which columns are numeric?
- Which conditions have higher or lower observed target values?
- Which variables are correlated in this dataset?
- Which points look unusual enough to review?
- What files and plots should go into a short analysis report?

This project packages that first-pass workflow so repeated CSV reviews are easier to reproduce.

## Features

- CSV input validation layer: file/extension checks, empty-file handling, duplicate column detection after header cleanup, and minimum-shape validation.
- Dataset profile helper: row/column counts, missing-value ratios, duplicate-row count, numeric summary, categorical summary, and conservative datetime-like column detection.
- EDA mode: missing-value summary, numeric summary, IQR outlier screening, correlation matrix, histograms, and correlation heatmap.
- Process mode: observed-row screening by target value, material-level summary, temperature-bin summary, and target correlation ranking.
- Multi-objective screening: simple min-max scoring across selected target columns.
- Reliability mode: summary tables and figures for thermal-cycle style reliability datasets.
- Smart-factory mode: simple 3-sigma anomaly candidate screening for process logs.
- SPC mode: I chart, moving range chart, and optional capability metrics when specification limits are provided.
- Simulation mode: regression-based what-if modeling for demo datasets, with clear caution that predictions do not guarantee experimental outcomes.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Quick Start

Run the default EDA workflow with the included demo process dataset:

```bash
python src/process_data.py --mode eda --input data/sample/experiment_process.csv --run-name demo_eda
```

Run process-condition screening on a target column:

```bash
python src/process_data.py --mode process --input data/sample/experiment_process.csv --target yield_percent --goal maximize --run-name demo_process
```

Run SPC analysis on the demo factory log:

```bash
python src/process_data.py --mode spc --input data/sample/factory_log.csv --target temperature_c --lsl 690 --usl 710 --run-name demo_spc
```

Run reliability summary on the included demo reliability dataset:

```bash
python src/process_data.py --mode reliability --input data/sample/experiment_reliability.csv --run-name demo_reliability
```

Run smart-factory log screening on the included demo factory log:

```bash
python src/process_data.py --mode smart_factory --input data/sample/factory_log.csv --run-name demo_smart_factory
```

Run the demo simulation workflow:

```bash
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_c process_time_min pressure_mpa thickness_um --scenario-input data/sample/simulation_scenarios.csv --run-name demo_simulation
```

Run the test suite:

```bash
pytest -q
```

## Demo Data Notice

The CSV files in `data/sample/` and `data/raw/` are small demo/synthetic datasets for exercising the workflow. They are not real equipment exports, production records, customer data, or validated experimental results.

The `data/raw/` folder currently contains demo/synthetic data only. See [`data/raw/README.md`](data/raw/README.md) before adding any real raw data.

The names and columns are intentionally engineering-like so the workflow can demonstrate materials/process analysis patterns. Any figures or reports generated from these files should be described as demo output only.

## Case Studies

Future real-data case studies can be documented under [`docs/case_studies/`](docs/case_studies/). A Markdown template is provided at [`docs/case_studies/case_study_template.md`](docs/case_studies/case_study_template.md).

At this stage, no real experimental, process, factory, customer, or production dataset is included. Case study writeups should clearly state the data source, whether the data is public or anonymized, the commands used, generated outputs, engineering interpretation, and limitations.

## Example Outputs

`outputs/` is ignored by Git because it contains local run artifacts. Representative README images are preserved in `docs/images/`.

### Correlation Heatmap

![Demo correlation heatmap](docs/images/correlation_heatmap.png)

### Process Group Summary Chart

![Demo material target mean chart](docs/images/material_target_mean.png)

### SPC Control Chart

![Demo SPC I chart](docs/images/spc_i_chart.png)

### Smart-Factory Trend Chart

![Demo smart-factory temperature trend](docs/images/smart_factory_temperature_trend.png)

Typical run output:

```text
outputs/{run_name}/processed/
outputs/{run_name}/figures/
outputs/{run_name}/reports/
```

## Limitations

- The included datasets are demo/synthetic data, not real experimental or factory data.
- Correlation values do not prove causation.
- Top and bottom condition tables are observed-row screening results, not process optimization.
- 3-sigma anomaly flags are first-pass review candidates, not confirmed fault diagnoses.
- SPC and capability outputs require appropriate sampling assumptions and specification limits.
- Regression-based simulation is a simple modeling aid for demo workflows and does not guarantee real experimental outcomes.
- This project does not perform XRD, SEM, or EDS analysis.
- The v0.2 data profile summarizes dataset structure and missingness only; it does not automatically validate engineering conclusions.

## Related Project

[`materials-characterization-analyzer`](https://github.com/jhin0410-lgtm/materials-characterization-analyzer) is a separate project for XRD, SEM, and EDS characterization data.

This project focuses on CSV-based experiment, process, quality, and reliability datasets. The characterization analyzer focuses on materials characterization equipment outputs such as spectra, images, and elemental composition tables.

## Future Work

- Add clearer input schema examples for common materials, process, reliability, battery, and OLED CSV formats.
- Extend the v0.2 data profile helper into optional report sections without changing the default CLI workflow.
- Add more focused report templates for different engineering dataset types.
- Add optional configuration files for selecting target columns and output naming.
- Improve documentation around interpreting SPC, screening, and regression outputs cautiously.
- Add more tests for CLI-level workflows and generated output files.