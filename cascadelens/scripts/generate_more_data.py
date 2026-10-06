"""Extra sample databases: scenarios that test grouping, consequences and noise.

Run: python cascadelens/scripts/generate_more_data.py
Reuses the helpers of generate_sample_data.py. The first four databases are not touched.
"""
import argparse
from datetime import date
from pathlib import Path

from generate_sample_data import add_retries, build, fail_cur, fail_ing, vary, verify_and_print

SAME_ERROR = ("Delta write failed: ConcurrentAppendException: Files were added to the table "
              "by a concurrent update. Activity ID: {guid}")


def same_error_three_tables(offset, ing, cur):
    """Three independent scripts fail with the same error text (the regex groups them)."""
    if offset == 0:
        for name in ("customer_dal", "sales_dal", "inventory_dal"):
            fail_cur(cur[name], vary(SAME_ERROR, cur[name]))


def same_cause_different_words(offset, ing, cur):
    """One cause (metastore down), three different error texts (the regex cannot group them)."""
    if offset == 0:
        fail_cur(cur["customer_dal"], "HiveMetaStoreClient: Could not connect to metastore at thrift://hms-01:9083. Connection refused.")
        fail_cur(cur["sales_dal"], "SocketTimeoutException: connect timed out after 60s reaching hive metastore hms-01.")
        fail_cur(cur["inventory_dal"], "HiveException: Unable to fetch table inventory_dal because the metastore is unavailable.")


def cascade_with_downstream_error(offset, ing, cur):
    """Sales ingestion fails AND sales_curation errors because of it, plus one independent failure."""
    if offset == 0:
        row = ing["sales_ingestion"][0]
        fail_ing(row, vary("Operation on target Ingest_sales_ingestion failed: HttpStatus 401: "
                           "Unauthorized from sales_api. Token expired. Activity ID: {guid}", row))
        fail_cur(cur["sales_curation"], "AnalysisException: cannot resolve 'order_id' given input columns [].")
        cur["sales_dal"]["rows_written"] = 0
        fail_cur(cur["inventory_dal"], "AnalysisException: cannot resolve 'reorder_level' given input columns [item_id, qty, warehouse].")


def recurring_plus_new(offset, ing, cur):
    """One defect on all 6 days, plus a new failure today with a confirmed victim."""
    fail_cur(cur["customer_dal"], vary("Natural key violation: duplicate customer_id values found. Job run id: {run}", cur["customer_dal"]))
    if offset == 0:
        fail_cur(cur["inventory_curation"], "Schema mismatch: column 'warehouse' expected string but found int in inventory.csv.")
        cur["inventory_dal"]["rows_written"] = 0


def retries_plus_one_real(offset, ing, cur):
    """Recovered retries in three ingestion pipelines (noise) plus one real curation failure."""
    if offset == 0:
        too_many = "Operation on target Ingest_sales_ingestion failed: HttpStatus 429: Too Many Requests from sales_api. Activity ID: {guid}"
        add_retries(ing["sales_ingestion"], [too_many, too_many])
        add_retries(ing["inventory_ingestion"], ["Operation on target Ingest_inventory_ingestion failed: TimeoutException: read of inventory.csv timed out after 120s. Started at {start}"])
        add_retries(ing["customer_ingestion"], ["Operation on target Ingest_customer_ingestion failed: ErrorCode=SqlTimeout: Execution timeout expired. Activity ID: {guid}"])
        fail_cur(cur["sales_curation"], "AnalysisException: cannot resolve 'discount_pct' given input columns [order_id, amount, region].")
        cur["sales_dal"]["rows_written"] = 0


def two_cascades(offset, ing, cur):
    """Two separate ingestion failures, each with its own downstream 0-row tables."""
    if offset == 0:
        row = ing["customer_ingestion"][0]
        fail_ing(row, vary("Operation on target Ingest_customer_ingestion failed: ErrorCode=SqlFailedToConnect: "
                           "Login failed for user 'svc_adf_crm'. Password expired. Activity ID: {guid}", row))
        row = ing["inventory_ingestion"][0]
        fail_ing(row, vary("Operation on target Ingest_inventory_ingestion failed: FileNotFoundException: "
                           "inventory.csv does not exist in the landing container. Activity ID: {guid}", row))
        for name in ("customer_curation", "customer_dal", "inventory_curation", "inventory_dal"):
            cur[name]["rows_written"] = 0


SCENARIOS = {
    "same_error_three_tables": (same_error_three_tables, 55),
    "same_cause_different_words": (same_cause_different_words, 56),
    "cascade_with_downstream_error": (cascade_with_downstream_error, 57),
    "recurring_plus_new": (recurring_plus_new, 58),
    "retries_plus_one_real": (retries_plus_one_real, 59),
    "two_cascades": (two_cascades, 60),
}

# Worked out by hand from the lineage rules, not computed by the code under test.
EXPECTED = {
    "same_error_three_tables": [
        "3 failures: customer_dal, inventory_dal, sales_dal. No impacted tables, recurrence 1 each.",
        "The regex puts all three in one signature group. Good wording says one shared cause.",
    ],
    "same_cause_different_words": [
        "3 failures: customer_dal, inventory_dal, sales_dal. No impacted tables, recurrence 1 each.",
        "Three different signatures, one real cause (metastore unavailable). Only a reader of the text sees it.",
    ],
    "cascade_with_downstream_error": [
        "2 failures: inventory_dal (no victims) and sales_ingestion (confirmed sales_dal, at risk sales_curation).",
        "sales_curation failed too, but it is a consequence, so it is NOT its own failure.",
    ],
    "recurring_plus_new": [
        "2 failures: customer_dal (recurrence 6) and inventory_curation (recurrence 1, confirmed inventory_dal).",
    ],
    "retries_plus_one_real": [
        "1 failure: sales_curation (confirmed sales_dal, recurrence 1). The three recovered retries are noise.",
        "Statuses: PL_01, PL_02 and PL_03 Succeeded with Issues, PL_04 Partially Failed.",
    ],
    "two_cascades": [
        "2 failures: customer_ingestion (confirmed customer_curation, customer_dal; at risk sales_curation, sales_dal)",
        "and inventory_ingestion (confirmed inventory_curation, inventory_dal).",
        "Statuses: PL_01 and PL_03 Failed, PL_02 Healthy, PL_04 Succeeded with Issues.",
    ],
}


def write_expected(out_dir: Path):
    lines = ["# Expected answers for the extra scenarios", ""]
    for name, details in EXPECTED.items():
        lines += [f"## {name}.db", ""] + [f"- {d}" for d in details] + [""]
    (out_dir / "expected_more.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-10-01", help="run date YYYY-MM-DD")
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"), help="output folder")
    args = ap.parse_args()
    today, out = date.fromisoformat(args.date), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (mutate, seed) in SCENARIOS.items():
        conn = build(out / f"{name}.db", mutate, seed, today)
        verify_and_print(name, conn, today)
        conn.close()
    write_expected(out)
    print(f"\nWrote {len(SCENARIOS)} .db files and expected_more.md to {out.resolve()}")


if __name__ == "__main__":
    main()