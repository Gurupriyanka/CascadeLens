# CascadeLens expected answers

Run date 2026-09-30 (today is the latest date in each .db).

Pipeline status rule, applied to today's units (latest attempt per unit): Failed = at least half of the units ended failed. Partial = some units failed, but fewer than half. Degraded = no unit failed, but a unit needed retries, or succeeded with 0 rows when history is normally non-zero. Healthy = everything succeeded first time with normal row counts.

## all_healthy.db

Nothing is wrong. The tool must not invent problems.

- Incident count: 0
- Pipeline statuses:
  - PL_01_Ingest_Crm: Healthy
  - PL_02_Ingest_Sales: Healthy
  - PL_03_Ingest_Inventory: Healthy
  - PL_04_Cur_Execute_Scripts: Healthy (6 of 6 succeeded)
- Route: status_only (no RCA, no fix proposals)

## clean_cascade.db

One CRM ingestion failure. No downstream script errors, the damage shows as 0 new rows. Inventory must stay clean.

- Incident count: 1
- Root cause: customer_ingestion failed in PL_01_Ingest_Crm, SQL login failed, password expired for svc_adf_crm. Confidence: high.
- Confirmed impacted (succeeded with 0 rows, failed upstream on the lineage): customer_curation, customer_dal.
- At risk (read stale customer data through the reference link, own row count normal): sales_curation, then sales_dal by transitivity. Lower confidence.
- Not affected: sales_ingestion, every Inventory table. They must NOT appear as victims.
- Pipeline statuses:
  - PL_01_Ingest_Crm: Failed
  - PL_02_Ingest_Sales: Healthy
  - PL_03_Ingest_Inventory: Healthy
  - PL_04_Cur_Execute_Scripts: Degraded (no failures, 2 of 6 scripts wrote 0 rows)
- Route: cross_layer_rca: ingestion -> curation -> semantic, detect impact by lineage and row-count anomaly, propose the fix at the ingestion root only

## noisy_recurring.db

Recovered ingestion retries (noise) plus one script that fails on its own every day.

- Incident count: 1 (customer_dal). The recovered sales_ingestion retries are noise and are not counted.
- Root cause: customer_dal references segment_code, which is not in its source customer_curation (columns are customer_id, name, city). Script defect, same error on all 6 days, upstream healthy. Confidence: high.
- Victims: none (nothing reads customer_dal).
- Noise: sales_ingestion failed twice (HTTP 429, timeout) and succeeded on attempt 3. One earlier 429 retry 2 days ago.
- Pipeline statuses:
  - PL_01_Ingest_Crm: Healthy
  - PL_02_Ingest_Sales: Degraded (needed 3 attempts)
  - PL_03_Ingest_Inventory: Healthy
  - PL_04_Cur_Execute_Scripts: Partial (1 of 6 scripts failed)
- Route: history_check -> single_layer_triage (semantic only), retries flagged as noise, no cross-layer trace

## ambiguous.db

Sales has two plausible causes and too little evidence. Inventory has a separate, clean failure.

- Incident count: 2
- Incident A (Sales): root cause undetermined, confidence low. Hypothesis 1: the sales source was empty or its schema changed upstream (sales_ingestion succeeded with 0 rows, normally about 9,800). Hypothesis 2: a defect in sales_curation. Victim: sales_dal (succeeded with 0 rows). Needs a human.
- Incident B (Inventory): root cause inventory_dal transformation error (reorder_level not in its source inventory_curation, which succeeded). Confidence: high. Victims: none.
- CRM chain is unaffected.
- Pipeline statuses:
  - PL_01_Ingest_Crm: Healthy
  - PL_02_Ingest_Sales: Degraded (succeeded with 0 rows, normally about 9,800)
  - PL_03_Ingest_Inventory: Healthy
  - PL_04_Cur_Execute_Scripts: Partial (2 of 6 scripts failed, sales_dal wrote 0 rows)
- Route: Incident A: cross_layer_rca -> low confidence -> escalate_to_human with both hypotheses. Incident B: single_layer_triage
