# Materials Data Analyzer

Materials Data Analyzer is a Python CSV analysis tool for materials experiments,
semiconductor process data, reliability data, smart-factory logs, and future
simulation workflows.

## Install

```powershell
pip install -r requirements.txt
```

## Basic Usage

Run the default EDA mode with the sample process file:

```powershell
python src/process_data.py
```

Run EDA:

```powershell
python src/process_data.py --mode eda --input data/sample/experiment_process.csv
```

Run process analysis to maximize yield:

```powershell
python src/process_data.py --mode process --input data/sample/experiment_process.csv --target yield_percent --goal maximize
```

Run process analysis to minimize resistivity:

```powershell
python src/process_data.py --mode process --input data/sample/experiment_process.csv --target resistivity_ohm_cm --goal minimize
```

Run multi-objective process screening:

```powershell
python src/process_data.py --mode process --input data/sample/experiment_process.csv --targets yield_percent hardness_hv resistivity_ohm_cm --goals maximize maximize minimize --run-name multi_objective_test
```

Run reliability analysis:

```powershell
python src/process_data.py --mode reliability --input data/sample/experiment_reliability.csv
```

Run smart-factory anomaly detection:

```powershell
python src/process_data.py --mode smart_factory --input data/sample/factory_log.csv
```

Run SPC control chart analysis:

```powershell
python src/process_data.py --mode spc --input data/sample/factory_log.csv --target temperature_c --run-name spc_temperature_test
```

Run SPC process capability analysis with specification limits:

```powershell
python src/process_data.py --mode spc --input data/sample/factory_log.csv --target temperature_c --lsl 690 --usl 710 --run-name spc_temperature_capability_test
```

Run regression-based simulation:

```powershell
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_c process_time_min pressure_mpa thickness_um --run-name simulation_yield_test
```

Run scenario-based what-if prediction:

```powershell
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_c process_time_min pressure_mpa thickness_um --scenario-input data/sample/simulation_scenarios.csv --goal maximize --run-name what_if_yield_test
```

## Output Structure

When `--run-name` is provided, results are saved under `outputs/{run_name}/`.
When it is omitted, the input CSV file name is used.

```text
outputs/{run_name}/processed/
outputs/{run_name}/figures/
outputs/{run_name}/reports/
```
