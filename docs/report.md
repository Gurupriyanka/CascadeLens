# CascadeLens report

## 1. Problem definition

When a data platform fails overnight, an engineer has to open ingestion, curation and semantic logs separately and work out which failure came first and what it broke. CascadeLens reads the three layers from one SQLite view, finds today's real failures, and lists the tables they affect. It does not guess at facts. Plain Python computes them, and AI agents choose the tools and write the root cause in plain English.

### Use case 1: a clean cascade (clean_cascade.db)

The CRM ingestion fails because a login password expired. Nothing downstream errors, but customer_curation and customer_dal wrote 0 rows. The tool should report one failure at customer_ingestion, list those two tables as confirmed impacted, and list sales_curation and sales_dal as at risk. Inventory must not appear.

### Use case 2: noise and a recurring defect (noisy_recurring.db)

sales_ingestion failed twice and then succeeded on a retry, which is noise. Separately, customer_dal fails every day with the same error. The tool should report one failure (customer_dal) with its recurrence, and not count the recovered retries.

### Use case 3: two failures in one run (ambiguous.db)

Sales has a failed curation script and an empty ingestion load, so the real cause is unclear. Inventory has a separate failure. The tool should report two independent failures, list sales_dal as impacted, and show the empty sales_ingestion load as a warning. It does not decide the Sales cause for the engineer.