# CascadeLens Step 2: Tools Reference

Step 2 is plain Python with no AI. Every function below becomes a tool for the agents in Step 3.
Examples use the sample databases in `cascadelens/scripts/data/`. The run date for all four is **2026-10-01** (the latest date in each database).

Examples were taken from outputs seen during the build. They are illustrations, not a fresh run.

## How the pieces fit together

```
read_logs
  -> recurrence_days            (on RAW records, before the noise filter)
  -> remove_recovered_failures  (noise filter, today's rows only)
  -> group_by_signature         (uses make_signature)
  -> pipeline_statuses          (uses latest_attempts, is_normally_non_zero, status_from_counts)
  -> build_downstream           (lineage graph)
analyse() runs all of this in one call.
find_impacted / split_impacted are used once a root cause is chosen (Step 3).
```

Design rule: the raw `error_message` on a record is never changed. The signature is only a grouping key.

---

## Data layer

### `read_logs(db_path)` in `cascadelens/reader.py`
Reads the `all_logs` view of a SQLite file and returns a `list[LogRecord]`.
Raises `FileNotFoundError` if the path does not exist (so a wrong path never silently creates an empty database) and `ValueError` if the query fails.

```python
records = read_logs("cascadelens/scripts/data/noisy_recurring.db")
len(records)   # 57 rows: 21 ingestion + 18 curation + 18 semantic
```

### `LogRecord` in `cascadelens/models.py`
A frozen dataclass for one log row with 18 fields. Only `layer` and `log_id` are required, the rest default to `None`.
`from_row` converts `start_time` and `end_time` to `datetime`. `is_failed` is a property (no brackets).

```python
record.is_failed     # True when status == "Failed"
record.start_time    # datetime(2026, 10, 1, 5, 18)
```

---

## Noise and signatures

### `remove_recovered_failures(records)` in `cascadelens/noise_filter.py`
One rule: a Failed record is noise if a later attempt Succeeded in the same `(run_id, unit_name)`. Returns the remaining records (succeeded rows are kept too).

```python
# today's sales_ingestion: attempt 1 Failed (429), attempt 2 Failed (timeout), attempt 3 Succeeded
# both failures are removed; the customer_dal failure stays
```

### `make_signature(message)` in `cascadelens/error_signature.py`
Turns a raw error into a stable text so the same problem groups together across days. Rules run in this order, each before the ones that would damage its input:

1. empty or None gives `""`
2. strip and lowercase
3. first line only
4. remove wrapper prefixes (`operation on target ... failed:`, `activity ... failed:`)
5. GUID to `<guid>`
6. timestamp to `<timestamp>`
7. compact date like 20260930 to `<date>`
8. non-empty bracket list to `[<list>]` (an empty `[]` is kept on purpose, it means the input table was empty)
9. numbers to `<num>`, but HTTP status codes and names like `sales_api_v2` are protected
10. collapse repeated spaces

```python
make_signature("Operation on target X failed: HttpStatus 429: Too Many Requests from sales_api. Activity ID: 3f2a9c1e-7b4d-4e2a-9c1f-0a1b2c3d4e5f")
# "httpstatus 429: too many requests from sales_api. activity id: <guid>"
```

Known limits: prefixes are removed once in list order (reversed stacking is not handled), and only the first line is used.

### `group_by_signature(records)` in `cascadelens/error_signature.py`
Groups failed records by signature. Records that did not fail are skipped. Uses `defaultdict(list)` internally and returns a plain dict.

```python
group_by_signature(records)
# {"analysisexception: cannot resolve 'segment_code' given input columns [<list>].": [6 records]}
```

### `recurrence_days(records, today, window_days=7)` in `cascadelens/error_signature.py`
Counts the distinct days each signature failed inside the window (today plus the 6 days before). Several failures on one day count once. Run it on raw records, so a recovering error such as the 429 still shows as recurring.

```python
recurrence_days(records, date(2026, 10, 1))
# segment_code: 6, the 429: 2, the timeout: 1
```

---

## Lineage

Edges come from the logs: curation `source_name` equals an ingestion `target_delta_table`, semantic `source_name` equals a curation `target_delta_table`, and curation `reference_source_name` is a second dependency.

### `build_downstream(records)` in `cascadelens/lineage.py`
Builds a dict from each table to the set of tables that read it directly. Ingestion rows are skipped because their source is an outside system.

```python
build_downstream(records)["customer_curation"]   # {"customer_dal", "sales_curation"}
```

### `find_impacted(downstream, failed_table)` in `cascadelens/lineage.py`
Walks the graph with a work list and a `seen` check, and returns everything below the failed table (not the table itself).

```python
find_impacted(downstream, "customer_ingestion")
# {"customer_curation", "customer_dal", "sales_curation", "sales_dal"}   (inventory never appears)
```

### `split_impacted(records, impacted, day)` in `cascadelens/lineage.py`
Splits the impacted set in two. **Confirmed**: succeeded today with 0 rows while its history is normally non-zero. **At risk**: everything else below the failure. A unit that did not run today lands in at risk.

```python
confirmed, at_risk = split_impacted(records, impacted, today)
# confirmed: {"customer_curation", "customer_dal"}
# at_risk:   {"sales_curation", "sales_dal"}
```

---

## Pipeline status

Rule applied to today's units, using the latest attempt per unit:

| Status | Meaning |
|---|---|
| Failed | at least half of the units failed |
| Partially Failed | some failed, fewer than half |
| Succeeded with Issues | none failed, but a unit needed a retry, or succeeded with 0 rows when its history is normally non-zero |
| Healthy | everything succeeded first time with normal row counts |

### `latest_attempts(records, day)` in `cascadelens/pipeline_status.py`
Keeps only the latest attempt per `(pipeline_name, unit_name)` for one day. Records are sorted by `start_time`, so a later record overwrites an earlier one.

```python
latest_attempts(records, today)[("PL_02_Ingest_Sales", "Ingest_sales_ingestion")].attempt   # 3
```

### `is_normally_non_zero(records, unit_key, day)` in `cascadelens/pipeline_status.py`
True if more than half of the unit's earlier, non-failed days wrote rows. A unit with no history returns False, so a 0 is not flagged. Missing `rows_written` counts as 0.

```python
is_normally_non_zero(records, ("PL_02_Ingest_Sales", "Ingest_sales_ingestion"), today)   # True in ambiguous.db
```

### `status_from_counts(total, failed, retried, zero_rows)` in `cascadelens/pipeline_status.py`
The decision ladder, first match wins. `failed * 2 >= total` means "at least half" without division. Raises `ValueError` for a pipeline with 0 units (that case is the future "Not run" detection).

```python
status_from_counts(6, 1, 0, 0)   # "Partially Failed"
status_from_counts(6, 3, 0, 0)   # "Failed" (exactly half counts as Failed)
```

### `pipeline_statuses(records, day)` in `cascadelens/pipeline_status.py`
Computes the four counts for each pipeline from the latest attempts, then applies the ladder. A unit counts as retried when it succeeded with `attempt > 1`. A missing `attempt` is treated as 1.

```python
pipeline_statuses(records, today)["PL_04_Cur_Execute_Scripts"]   # "Partially Failed" in noisy_recurring
```

---

## One call for everything

### `analyse(db_path)` in `cascadelens/analysis.py`
Runs the flow in the agreed order and returns a frozen `Analysis` with five fields: `today`, `statuses`, `failure_groups`, `recurrence`, `downstream`.
`today` is the latest date in the database (nothing is hardcoded). Recurrence uses raw records. The noise filter and grouping use today's rows only.

```python
result = analyse("cascadelens/scripts/data/all_healthy.db")
result.failure_groups   # {} (the tool does not invent problems)
```

---

## Verified results on the four databases

| Database | Pipeline statuses (PL_01 / PL_02 / PL_03 / PL_04) | Failures after noise filter |
|---|---|---|
| all_healthy | Healthy / Healthy / Healthy / Healthy | none |
| clean_cascade | Failed / Healthy / Healthy / Succeeded with Issues | customer_ingestion (password expired) |
| noisy_recurring | Healthy / Succeeded with Issues / Healthy / Partially Failed | customer_dal (segment_code, 6 days) |
| ambiguous | Healthy / Succeeded with Issues / Healthy / Partially Failed | sales_curation, inventory_dal |

## Not built yet

- `analyse` does not call `split_impacted`, because that needs a chosen root cause (Step 3).
- Open limits: reversed prefix stacking, first line only, signature tuning on real DiLog and FwkCurLog messages, and "Not run" detection.
- Tests: 40 passing. Unit tests per function, plus end-to-end tests on all four databases.
