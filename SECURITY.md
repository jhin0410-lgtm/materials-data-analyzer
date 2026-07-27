# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch. Historical releases and research snapshots are not guaranteed to receive backported fixes.

## Reporting a vulnerability

Do not disclose credentials, exploit details, private datasets, or other sensitive information in a public issue.

Use GitHub's private vulnerability reporting or Security Advisory workflow for this repository when that option is available. If private reporting is unavailable, open a public issue containing only a minimal, non-sensitive description and request a private contact channel. Do not include proof-of-concept code or secrets in that issue.

Include the following in a private report when possible:

- affected version, commit, command, or component;
- impact and realistic attack conditions;
- minimal reproduction steps;
- whether credentials, local files, generated artifacts, or external connectors are involved;
- suggested mitigation, if known.

## Credential exposure

If a real credential is ever committed, removing it from the current branch is not sufficient. Revoke or rotate the credential immediately, then remove it from Git history where appropriate. Treat any credential present in a public commit as compromised.

## Scope

Scientific disagreement, unsupported interpretation, data-quality limitations, and model-performance concerns are important but are not security vulnerabilities. Report those through a normal issue with reproducible evidence and without sharing restricted data.
