# Domain Knowledge Packs

Status: `scaffold_stage` for v2.1.3.

Domain knowledge packs group variable definitions, assumptions, mechanism
metadata, feature candidates, caution statements, and scientific constraint IDs.
They are explicit metadata, not executable plugins.

## Registered Packs

| Pack | Domain | Current role |
| --- | --- | --- |
| `materials_basic_v1` | Materials | Composition fractions, calculated-property units, descriptor candidates, and thermodynamic claim cautions. |
| `battery_degradation_basic_v1` | Battery | Capacity, efficiency, cycle, temperature, and degradation-feature metadata. |
| `manufacturing_process_basic_v1` | Manufacturing | Process-window, flow, setpoint, and sensor-semantics metadata. |
| `reliability_degradation_basic_v1` | Reliability | Asset history, event/censoring, degradation trajectory, and post-event leakage boundaries. |
| `xrd_crystallography_basic_v1` | XRD | Bragg and Scherrer metadata checks with crystallite-size claim boundaries. |

## Use

```powershell
python -m src.cli list-knowledge-packs
python -m src.cli inspect-knowledge-pack materials_basic_v1
```

## Claim Boundary

Knowledge packs can support future feature engineering and diagnostics, but
they do not by themselves prove:

- physical mechanism validity
- synthesizability
- degradation root cause
- calibrated operational probabilities
- production readiness
- robust cross-domain generalization

The current packs preserve cautions such as: energy-above-hull is not
synthesizability, Scherrer estimates crystallite size rather than particle
size, and anonymous SECOM features cannot be assigned process physics without
semantic metadata.
