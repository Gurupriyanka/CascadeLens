# Expected answers for the extra scenarios

## same_error_three_tables.db

- 3 failures: customer_dal, inventory_dal, sales_dal. No impacted tables, recurrence 1 each.
- The regex puts all three in one signature group. Good wording says one shared cause.

## same_cause_different_words.db

- 3 failures: customer_dal, inventory_dal, sales_dal. No impacted tables, recurrence 1 each.
- Three different signatures, one real cause (metastore unavailable). Only a reader of the text sees it.

## cascade_with_downstream_error.db

- 2 failures: inventory_dal (no victims) and sales_ingestion (confirmed sales_dal, at risk sales_curation).
- sales_curation failed too, but it is a consequence, so it is NOT its own failure.

## recurring_plus_new.db

- 2 failures: customer_dal (recurrence 6) and inventory_curation (recurrence 1, confirmed inventory_dal).

## retries_plus_one_real.db

- 1 failure: sales_curation (confirmed sales_dal, recurrence 1). The three recovered retries are noise.
- Statuses: PL_01, PL_02 and PL_03 Succeeded with Issues, PL_04 Partially Failed.

## two_cascades.db

- 2 failures: customer_ingestion (confirmed customer_curation, customer_dal; at risk sales_curation, sales_dal)
- and inventory_ingestion (confirmed inventory_curation, inventory_dal).
- Statuses: PL_01 and PL_03 Failed, PL_02 Healthy, PL_04 Succeeded with Issues.
