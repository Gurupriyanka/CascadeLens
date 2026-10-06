# CascadeLens triage report

- **Database:** cascadelens/scripts/data/clean_cascade.db
- **Overall status:** Unhealthy

## Failure 1: customer_ingestion

- **Root cause:** SQL connection error related to an expired password.
- **Recurrence:** 1 of the last 7 days

**Confirmed impacted**

- customer_curation
- customer_dal

**At risk**

- sales_curation
- sales_dal
