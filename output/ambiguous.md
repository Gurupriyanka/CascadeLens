# CascadeLens triage report

- **Database:** cascadelens/scripts/data/ambiguous.db
- **Overall status:** Unhealthy

## Failure 1: sales_curation

- **Root cause:** AnalysisException: cannot resolve 'order_id' given input columns [].
- **Recurrence:** 1 of the last 7 days

**Confirmed impacted**

- sales_dal

## Failure 2: inventory_dal

- **Root cause:** AnalysisException: cannot resolve 'reorder_level' given input columns [item_id, qty, warehouse].
- **Recurrence:** 0 of the last 7 days

## Warnings

- PL_02_Ingest_Sales: sales_ingestion loaded 0 rows, at risk: sales_curation, sales_dal
