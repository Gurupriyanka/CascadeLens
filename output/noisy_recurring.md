# CascadeLens triage report

- **Database:** cascadelens/scripts/data/noisy_recurring.db
- **Overall status:** Unhealthy

## Failure 1: customer_dal

- **Root cause:** Spark SQL job cannot find the 'segment_code' column in the provided input columns.
- **Recurrence:** 6 of the last 7 days
