# CascadeLens triage report

- **Database:** cascadelens/scripts/data/noisy_recurring.db
- **Overall status:** Unhealthy

## Failure 1: customer_dal

- **Root cause:** The query attempted to reference the 'segment_code' column, which is not available in the input columns.
- **Recurrence:** 6 of the last 7 days
