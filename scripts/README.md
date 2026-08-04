# Script Index

Scripts are workflow entry points and deterministic artifact utilities. They are
not all interchangeable commands, and many are tied to one source, case study,
or historical release contract.

Prefer installed CLIs for reusable analyzer behavior. Use a script when its
bounded workflow and prerequisites match the task.

## Primary Local Workflows

| Script | Purpose | Mutates scientific inputs? |
|---|---|---|
| `run_nasa_pcoe_battery_pipeline.ps1` | import the official local NASA archive, run Battery Intelligence, and refresh protocol diagnostics | creates new import and analysis outputs; does not rewrite source archive |
| `run_nasa_pcoe_review_workflow.ps1` | refresh protocol audit, binding, queue, and evidence from existing artifacts | no model fitting or source repair |
| `close_nasa_pcoe_audit.ps1` | verify completed disposition binding, finalize 34 reviews, and package the closed audit bundle | no model fitting or reviewer inference |
| `run_representative_process_characterization_workflow.py` | build the verified NIST process-characterization case, design audit, and bounded next-experiment plan | no response model or optimization |
| `run_nist_ambench_2018_02_workflow.py` | build and verify the NIST AM-Bench integrated case | no model training |
| `consume_characterization_handoff_bundle.py` | validate and consume a checksum-bound characterization bundle | no row-order join or metric recomputation |
| `run_tests.ps1` | execute the repository test suite | test outputs and caches only |

## NASA PCoE Utilities

### Acquisition and analysis

- `download_nasa_pcoe_battery_dataset.ps1`
- `run_nasa_pcoe_battery_pipeline.ps1`

### Existing-artifact review

- `run_nasa_pcoe_protocol_audit.ps1`
- `run_nasa_pcoe_review_queue.ps1`
- `run_nasa_pcoe_review_evidence.ps1`
- `run_nasa_pcoe_review_workflow.ps1`
- `run_nasa_pcoe_review_disposition.ps1`

### Closeout and packaging

- `close_nasa_pcoe_audit.ps1`
- `package_nasa_pcoe_full_audit.ps1`
- `prepare_nasa_pcoe_full_audit.py`

The preferred final closeout entry point is `close_nasa_pcoe_audit.ps1`. The
individual scripts remain available for diagnosis, partial review, and backward
compatibility.

## Dataset Construction

Scripts beginning with `build_` create deterministic tables, manifests, or case
study packages from declared inputs. Major groups include:

- Battery Archive inventory, normalization, analysis-ready, and case-study
  builders;
- Kaggle NASA battery summaries and discharge features;
- Materials Project query, normalization, descriptors, and characterization
  handoff builders;
- Smart Factory and Reliability acquisition builders;
- NIST AM-Bench case-study and characterization-handoff builders.

A successful build establishes software behavior for the supplied inputs. It
does not by itself establish cross-source comparability or model validity.

## Analysis and Validation

Scripts beginning with `run_` execute a bounded analysis or validation workflow.
Examples include:

- Materials Project screening, validation, and trust analysis;
- Smart Factory classification and trust analysis;
- Reliability classification and trust analysis;
- representative process-characterization and NIST workflows;
- NASA pipeline, review, and closeout workflows.

Check the corresponding documentation before running a script. Some workflows
require local datasets or API credentials; others are intentionally offline.

## Read-only Audits and Verification

Scripts beginning with `audit_`, `verify_`, or `check_` generally inspect
existing files and emit audit evidence without retraining models or rewriting
source measurements. Examples include:

- Battery Archive schema audit;
- NIST process-design audit and case verification;
- cross-repository release-readiness audit;
- public-repository hygiene checks;
- v2.7 release-candidate and publication verification;
- processed-data and Excel dataset inspection.

Read the script contract rather than relying only on its prefix. A verification
script may still write a new report or manifest into a selected output directory.

## Acquisition and Connectors

- `acquire_materials_project_v1_3.py`
- `ingest_data.py`
- `download_nasa_pcoe_battery_dataset.ps1`

Acquisition requires explicit source, credential, license, and checksum review.
Do not commit credentials, raw API responses, downloaded source archives, or
private local configuration.

## Release and Historical Workflows

Release-specific scripts preserve versioned evidence and publication contracts.
Examples include:

- `audit_v2_7_public_release_candidate.py`;
- `promote_v2_7_public_release.py`;
- `verify_v2_7_promotion.py`;
- `verify_v2_6_14_external_evidence_line_closeout.py`;
- `write_v2_6_14_external_evidence_line_closeout.py`.

Do not use these as general current-analysis commands. Exact paths, versions,
checksums, and negative scientific conclusions may be part of their release
contract.

## Selection Rule

Use this order when choosing an entry point:

1. installed CLI documented in the root README;
2. current end-to-end `run_*` or `close_*` workflow;
3. specific `build_*` utility when constructing one artifact family;
4. `audit_*`, `verify_*`, or `check_*` command for existing-artifact validation;
5. release-specific command only for the exact release contract.

Do not run broad groups of scripts automatically. Preserve source data, local
provenance, negative results, and existing public behavior.

## Related Documentation

- [`docs/REPOSITORY_NAVIGATION.md`](../docs/REPOSITORY_NAVIGATION.md)
- [`docs/WORKSPACE_HYGIENE.md`](../docs/WORKSPACE_HYGIENE.md)
- [`docs/NASA_PCOE_AUDIT_CLOSEOUT.md`](../docs/NASA_PCOE_AUDIT_CLOSEOUT.md)
- [`docs/OUTPUTS_POLICY.md`](../docs/OUTPUTS_POLICY.md)
