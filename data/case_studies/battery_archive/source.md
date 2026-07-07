# Battery Archive Source Template

## Source

- Endpoint:
- Base URL:
- API key environment variable: `BATTERY_ARCHIVE_API_KEY`
- License:
- Citation:
- Schema:
- Access date:

## Ingestion

```bash
python scripts/ingest_data.py --source battery_archive --limit 50
```

## Notes

The Battery Archive connector is a generic REST skeleton until endpoint and
schema documentation are finalized. Fill in endpoint, license, citation, and
schema details before publishing any case study.
