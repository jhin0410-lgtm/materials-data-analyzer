# Security Policy

## Supported Version

Security-related fixes are applied to the current `main` branch. Historical
commits, tags, generated artifacts, and external datasets are not maintained as
supported software releases unless a release note states otherwise.

## Reporting a Vulnerability

Do not post credentials, private data, exploit details, or unpublished
vulnerability information in a public issue.

Use GitHub private vulnerability reporting when it is available for this
repository. If private reporting is unavailable, open a minimal public issue
asking the repository owner to establish a private contact channel. Do not
include sensitive technical details in that issue.

For non-sensitive security hardening requests, a normal GitHub issue is
appropriate.

## Secrets and Local Data

This repository must not contain API keys, passwords, access tokens, private
keys, local `.env` files, Kaggle credentials, private paths, or downloaded raw
datasets. Local secrets must be supplied through ignored files or environment
variables. Raw and generated data must follow the policies in `.gitignore` and
`docs/PUBLIC_REPOSITORY_POLICY.md`.

## Research Software Boundary

This project is research and portfolio software. It is not a production
security control, safety system, regulated decision engine, or hosted service.
A successful test run does not establish deployment security.
