# README Example Images

This folder stores representative images used by the project README. They are copied from demo runs so the README can show stable visual examples without committing the full `outputs/` directory.

The images are based on demo/synthetic data, not real experimental, factory, customer, or production data.

## Image Sources

| Image | Demo command that generates the source output |
| --- | --- |
| `correlation_heatmap.png` | `python src/process_data.py --mode eda --input data/sample/experiment_process.csv --run-name demo_eda` |
| `material_target_mean.png` | `python src/process_data.py --mode process --input data/sample/experiment_process.csv --target yield_percent --goal maximize --run-name demo_process` |
| `spc_i_chart.png` | `python src/process_data.py --mode spc --input data/sample/factory_log.csv --target temperature_c --lsl 690 --usl 710 --run-name demo_spc` |
| `smart_factory_temperature_trend.png` | `python src/process_data.py --mode smart_factory --input data/sample/factory_log.csv --run-name demo_smart_factory` |

`outputs/` is intentionally ignored by Git because it contains local run artifacts. Keep only selected README-ready images here.