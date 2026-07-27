# Raw Data Folder Policy

`data/raw/` is a local staging area. Its contents are ignored by Git; only this policy file is tracked.

Do not commit unpublished research data, proprietary process data, institution-owned confidential data, customer or company data, personal data, credentials, or datasets whose redistribution terms do not permit publication.

Before using an external dataset, record:

- source and stable identifier or URL;
- license, access terms, and redistribution constraints;
- retrieval date or snapshot information;
- original schema, units, and measurement context;
- preprocessing, filtering, exclusions, and generated derivatives;
- known quality, comparability, and scientific limitations.

Synthetic demonstration data that must be versioned belongs under `data/sample/`. Compact, source-documented summaries may be placed under `data/processed/` or the relevant case-study directory when they are necessary for reproducibility and permitted for redistribution.

Never join or identify records by row order or inferred filenames when stable identifiers are available.
