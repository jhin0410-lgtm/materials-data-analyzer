# Public Repository Policy

## Scope

This repository is public research software and portfolio material. The root
MIT license covers original source code and original documentation in this
repository unless a file states otherwise.

External datasets, publications, figures, standards, and third-party software
retain their own licenses, terms of use, and citation requirements. The MIT
license does not relicense those materials.

## Tracked Content

The repository may track:

- source code and tests;
- synthetic examples clearly identified as synthetic;
- compact derived tables when redistribution is permitted;
- source manifests, checksums, schemas, and citation records;
- aggregate or identity-free analysis summaries;
- documentation of negative, limited, or inconclusive results.

## Local-Only Content

The following must remain local and ignored unless a specific source review
explicitly authorizes redistribution:

- downloaded raw datasets and archives;
- row-level predictions or large generated outputs;
- credentials, API keys, access tokens, private keys, and `.env` files;
- private or institution-restricted data;
- absolute local paths and user-specific configuration;
- proprietary instrument exports;
- files containing personal or confidential information.

## External Data Requirements

Every real-data case study must document:

1. the official source and persistent identifier when available;
2. the accessed version or access date;
3. the source license or terms-of-use status;
4. which files are redistributed and why redistribution is allowed;
5. which files remain local;
6. relevant preprocessing, exclusions, units, and scientific limitations.

A source that is inaccessible, ambiguously licensed, or missing essential
metadata is placed on hold after one bounded screening stage. Access failure
must not expand into repeated gate-only feature versions.

## Provenance and Scientific Claims

Tracked derived values must be traceable to a documented source or to a
reproducible local transformation. Missing metadata is not inferred.

Software validation and scientific validation are reported separately. Passing
tests establishes that code behavior is reproduced; it does not establish
physical comparability, calibration, causal interpretation, external
generalization, or engineering-decision readiness.

## Public Release Checklist

Before merging a public-facing change:

- run the full test suite;
- run `python scripts/check_public_repository_hygiene.py`;
- confirm `git status --short` is clean;
- inspect the diff for secrets, raw data, private paths, and generated files;
- document source and license information for new external data;
- preserve existing public interfaces unless a migration is documented.
