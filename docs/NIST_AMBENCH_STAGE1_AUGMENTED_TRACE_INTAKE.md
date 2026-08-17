# NIST AM-Bench 2018-02 Stage 1 Augmented-Trace Intake

## Purpose

This workflow closes the software intake/audit gap tracked by issue #154. It is a
separate path from `run_representative_process_characterization_workflow.py`;
the frozen ten-trace representative case remains unchanged.

The workflow is intentionally **Diagnostic**. It validates bytes, provenance
bindings, identity joins, predeclared process-cell coverage, and structural
estimability. It does not operate equipment, fetch network data, generate
synthetic responses, fit a model, optimize a process, or promote scientific
status.

## Entry point

```powershell
python scripts/run_nist_ambench_augmented_trace_intake.py `
  --manifest C:\path\to\intake\manifest.json `
  --intake-root C:\path\to\intake `
  --output C:\path\to\new-output
```

The manifest must be contained by `--intake-root`, and every referenced source
artifact must use a relative POSIX path contained by the same root.

## Manifest contract

Top level:

```json
{
  "schema_version": "1.0",
  "contract_id": "nist_ambench_2018_02_stage1_augmented_trace_intake",
  "process_records": [],
  "characterization_records": []
}
```

Each process record must explicitly bind:

- unique `sample_id` and `trace_id`;
- the predeclared `condition_id`, build, run, and block;
- target laser power and achieved calibrated laser power as separate values;
- exact process units (`W`, `mm/s`);
- controlled-settings, machine, optics, calibration, calibration-reference, and
  control-software identities;
- IN625 material lot, geometry, preparation history, and spatial location;
- evidence/source semantics and source authority/reference/record identity;
- a root-contained raw artifact with declared SHA-256 and byte size;
- deviation, interruption, censoring, failed-acquisition, saturation, and
  exclusion status.

Each characterization record independently binds:

- the same explicit `sample_id` and `trace_id`;
- method, acquisition-settings, preprocessing, exclusion-policy, and
  measurement-schema identities;
- one or more explicit `{name, value, unit}` measurements;
- evidence/source semantics and authority/reference/record identity;
- its own checksum-bound raw artifact;
- the same explicit acquisition-status schema.

There is no filename join, row-order join, interpolation, unit conversion,
aggregation, outlier removal, or silent exclusion.

## Predeclared Stage 1 cells

Only the three issue-#76 Stage 1 cells are accepted by this contract:

| Condition ID | Target power | Scan speed | Minimum traceable records |
|---|---:|---:|---:|
| `stage1_p137_9_v800` | 137.9 W | 800 mm/s | 3 |
| `stage1_p137_9_v1200` | 137.9 W | 1200 mm/s | 3 |
| `stage1_p179_2_v400` | 179.2 W | 400 mm/s | 3 |

Unapproved extra or midpoint conditions fail closed rather than silently
satisfying Stage 1. Records within one condition must also agree on one explicit
achieved calibrated power; the workflow will not silently pool differing
achieved-power conditions.

## Byte and path provenance

The intake reads the manifest as exact bytes and records a raw SHA-256. It also
records an order-normalized canonical manifest SHA-256 so process and
characterization array order does not alter the semantic binding.

Every unique referenced artifact is read once. SHA-256 and byte size are
computed from those same bytes and compared with the supplied binding. Absolute
paths, Windows drive paths, `..` traversal, missing files, symlink targets that
escape the intake root, checksum mismatches, and size mismatches fail closed.

The raw manifest hash is intentionally byte-order sensitive. Reordering JSON
records therefore changes the raw-byte hash while leaving the normalized record
ordering and canonical semantic hash unchanged.

## Identity and status preservation

Process and characterization arrays are validated independently. Each side must
have unique `sample_id` and unique `trace_id`, and the complete
`(sample_id, trace_id)` sets must match exactly before a one-to-one join is
created.

Censored, failed, saturated, excluded, interrupted, or deviation-marked records
remain in the validated provenance table. They are not silently dropped.
Conservatively, any such status makes that trace ineligible for the structural
replicate count, while the row remains in the augmented table and report.

## Frozen baseline and structural audit

After intake preflight succeeds, the separate workflow regenerates the existing
frozen ten-trace NIST case through the existing case-study code, without
modifying the tracked baseline source evidence. It then:

1. writes the validated Stage 1 joined records;
2. combines them with the frozen ten-trace baseline;
3. retains failed/censored rows in the augmented provenance table;
4. creates an explicit structurally eligible audit subset;
5. reruns `audit_nist_ambench_2018_02_process_design.py`.

The design audit now derives interaction estimability from the actual design
matrix rank. A complete two-power × three-speed grid can therefore report a
full-rank four-parameter interaction design. For the intended 19-trace
structure, this is rank 4 with 15 sample-level residual degrees of freedom.

This is **structural estimability only**. The audit explicitly states that
estimability is not evidence that an interaction effect exists.

## Scientific trust boundary

`measured_physical_candidate` is a provenance category, not independent proof
of physical origin. Even if all nine records are self-declared measured and
fully checksum-bound, the software reports:

- declared measured-candidate coverage separately;
- `physical_origin_authenticated_by_software: false`;
- `scientific_stage1_complete: false`.

Software can authenticate exact bytes and internal provenance consistency. It
cannot, from self-declared metadata alone, prove that an instrument physically
generated those bytes or establish the scientific validity of their values.

Therefore **issue #76 remains open** until the required real physical traces
and authoritative provenance actually exist and their origin is independently
established. Synthetic, reference-only, or diagnostic fixtures may exercise the
structural path but cannot satisfy that scientific requirement.

## Regression and failure modes

The dedicated tests cover:

- frozen three-condition audit regression;
- 19-trace / six-cell / rank-4 / residual-df-15 structural fixture;
- manifest-order-independent joined output and canonical binding;
- duplicate and mismatched identities;
- checksum and byte-size mismatch;
- root traversal;
- missing calibration provenance;
- changed process and characterization units;
- unapproved midpoint conditions;
- censor-state preservation and non-counting;
- fewer than three usable traces in a Stage 1 cell;
- synthetic evidence not satisfying measured/physical readiness;
- self-declared measured records never authenticating physical origin by
  themselves.
