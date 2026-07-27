# Licensing and Third-Party Data Notice

## Repository License

Unless a file states otherwise, the original source code and original
documentation in this repository are licensed under the MIT License in
[`LICENSE`](LICENSE).

## Third-Party Data and Upstream Materials

The MIT License does **not** relicense third-party datasets, upstream software,
published figures, papers, trademarks, or other externally sourced materials.
Those materials remain subject to their original terms, licenses, citation
requirements, and access restrictions.

This repository contains workflows and compact derived artifacts associated
with external data families such as:

- NASA/Kaggle battery-aging data;
- Battery Archive datasets;
- Materials Project records;
- UCI SECOM process-quality data;
- Backblaze drive-reliability data.

Raw downloaded datasets and large source archives are not intended to be
committed. Source-specific case-study documentation records the relevant
provenance, access route, and scientific limitations. Users are responsible for
reviewing the upstream terms before downloading, redistributing, publishing, or
commercially using any external dataset.

## Generated and Derived Artifacts

Files under `outputs/` are regenerable local artifacts and are ignored by Git.
Tracked compact summaries are retained for reproducibility and review, but they
do not transfer ownership of the underlying source data and must not be treated
as a substitute for the original dataset or its documentation.

## Scientific and Engineering Use

The software and examples are research and engineering-analysis aids. They do
not provide certified measurements, calibrated uncertainty, production control,
medical advice, safety approval, or autonomous engineering decisions. Users
must validate sample identity, units, measurement conditions, preprocessing,
comparability, target definitions, leakage risks, and claim scope for their own
application.
