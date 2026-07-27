# Security Policy

## Supported Version

Security fixes are applied to the latest commit on `main`. Historical branches,
local experimental artifacts, and unmerged feature branches are not supported.

## Reporting a Vulnerability

Do not open a public issue containing credentials, private data, exploit details,
or information that would make an active vulnerability easier to abuse.

Use GitHub's private vulnerability-reporting or Security Advisory workflow for
this repository when available. If private reporting is unavailable, contact the
repository owner through the contact method listed on the owner's GitHub profile
before sharing sensitive details publicly.

A useful report includes:

- the affected commit, module, or command;
- a minimal reproduction using synthetic or non-sensitive data;
- the expected and observed behavior;
- the potential confidentiality, integrity, or availability impact;
- suggested mitigations, when known.

Never include real API keys, access tokens, proprietary datasets, patient data,
export-controlled information, or employer-confidential material in a report.

## Credential Exposure

If a credential is accidentally committed, treat it as compromised even after
the file is deleted. Revoke or rotate it immediately, then remove it from Git
history using an appropriate history-rewrite procedure and review dependent
systems for misuse.

## Scope Notes

Scientific disagreement, weak model performance, unsupported causal claims, or
missing experimental metadata are scientific-quality issues rather than software
security vulnerabilities. They should still be reported, but without using the
private security channel unless sensitive information is involved.

This project is a local research and engineering-analysis framework, not a
production control system or security boundary. Users remain responsible for
access control, data governance, environment isolation, and validation in their
own deployments.
