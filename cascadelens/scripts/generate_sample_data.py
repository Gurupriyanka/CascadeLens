#!/usr/bin/env python3
"""CascadeLens - sample data generator (Step 1, v2).

Creates two log tables that mimic the real ones:
  DiLog      ingestion runs (ADF pipeline + Databricks notebook)
  FwkCurLog  curation and semantic scripts (PL_04_Cur_Execute_Scripts)
and a view, all_logs, that unifies them with lineage columns.

Three chains (layer tables are named after their layer):
  CRM        customer_ingestion -> customer_curation -> customer_dal
  Sales      sales_ingestion    -> sales_curation    -> sales_dal
             sales_curation also READS customer_curation (reference dependency)
  Inventory  inventory_ingestion -> inventory_curation -> inventory_dal
             fully independent of CRM and Sales (proves there is no false cascade)

Layer rule: FwkCurLog scripts with _dal in the name are semantic, the rest are curation.

Cross-layer link (run IDs are NOT shared across layers):
  curation.source_name == ingestion.target_delta_table
  semantic.source_name == curation.target_delta_table
  curation.reference_source_name = a second table the script reads for details

Realistic behaviour: curation and semantic scripts read existing Delta tables, so when
ingestion fails they still SUCCEED, just with 0 new rows. They only FAIL on their own
problems (natural key duplicates, transformation errors, schema mismatch).

Usage:
  python generate_sample_data.py                  # writes 4 .db files + expected_answers.md
  python generate_sample_data.py --date 2026-09-30
  python generate_sample_data.py --out ./data
"""
import argparse
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import uuid

HISTORY_DAYS = 5  # healthy days before "today"
CUR_PIPELINE = "PL_04_Cur_Execute_Scripts"

DDL = r"""
DROP VIEW  IF EXISTS all_logs;
DROP TABLE IF EXISTS DiLog;
DROP TABLE IF EXISTS FwkCurLog;

CREATE TABLE DiLog (
    log_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    pipeline_name       TEXT NOT NULL,
    activity_name       TEXT NOT NULL,
    notebook_name       TEXT,
    trigger_name        TEXT,
    status              TEXT NOT NULL,      -- Succeeded | Failed
    error_message       TEXT,
    start_time          TEXT NOT NULL,
    end_time            TEXT NOT NULL,
    rows_written        INTEGER,
    attempt             INTEGER NOT NULL DEFAULT 1,
    source_type         TEXT,
    source_name         TEXT,
    target_type         TEXT,
    target_delta_table  TEXT
);

CREATE TABLE FwkCurLog (
    log_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                TEXT NOT NULL,
    pipeline_name         TEXT NOT NULL,
    script_name           TEXT NOT NULL,
    status                TEXT NOT NULL,    -- Succeeded | Failed
    error_message         TEXT,
    start_time            TEXT NOT NULL,
    end_time              TEXT NOT NULL,
    rows_written          INTEGER,
    source_type           TEXT,
    source_name           TEXT,
    reference_source_name TEXT,             -- second table read for details, else NULL
    target_type           TEXT,
    target_delta_table    TEXT
);

DROP VIEW IF EXISTS all_logs;
CREATE VIEW all_logs AS
SELECT 'ingestion' AS layer, log_id, run_id, pipeline_name,
       activity_name AS unit_name, notebook_name, trigger_name,
       status, error_message, start_time, end_time, rows_written, attempt,
       source_type, source_name, NULL AS reference_source_name,
       target_type, target_delta_table
FROM DiLog
UNION ALL
SELECT CASE WHEN script_name LIKE '%\_dal%' ESCAPE '\' THEN 'semantic' ELSE 'curation' END,
       log_id, run_id, pipeline_name,
       script_name, NULL, NULL,
       status, error_message, start_time, end_time, rows_written, 1,
       source_type, source_name, reference_source_name,
       target_type, target_delta_table
FROM FwkCurLog;
"""

# (pipeline, source_type, source_name, target table, normal rows)
INGEST = [
    ("PL_01_Ingest_Crm",       "sqlserver", "crm.dbo.customer",    "customer_ingestion",  1500),
    ("PL_02_Ingest_Sales",     "api",       "sales_api/orders",    "sales_ingestion",     9800),
    ("PL_03_Ingest_Inventory", "csv",       "inventory.csv",       "inventory_ingestion", 2300),
]

# (script = target table, source table, reference table, normal rows); _dal = semantic
CURATE = [
    ("customer_curation",  "customer_ingestion",  None,                "customer_curation",  1500),
    ("sales_curation",     "sales_ingestion",     "customer_curation", "sales_curation",     9800),
    ("inventory_curation", "inventory_ingestion", None,                "inventory_curation", 2300),
    ("customer_dal",       "customer_curation",   None,                "customer_dal",       1500),
    ("sales_dal",          "sales_curation",      None,                "sales_dal",           320),
    ("inventory_dal",      "inventory_curation",  None,                "inventory_dal",        75),
]


def ts(d: date, hour: int, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute)


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def vary(msg, row, salt=0):
    """Fill {guid}, {run} and {start} in a message so the same problem reads
    differently on every day, like real ADF and Databricks errors."""
    unit = row.get("activity_name") or row.get("script_name")
    guid = uuid.uuid5(uuid.NAMESPACE_DNS, f"{row['run_id']}|{unit}|{salt}")
    run = 880000 + guid.int % 90000
    return msg.format(guid=guid, run=run, start=row["start_time"])

def baseline_day(day: date, rng: random.Random):
    """One healthy day. Returns (ingestion: table -> list of attempt rows, curation: script -> row)."""
    ing, cur = {}, {}
    for i, (pipe, stype, sname, target, base) in enumerate(INGEST):
        start = ts(day, 2, 0) + timedelta(minutes=10 * i)
        end = start + timedelta(minutes=rng.randint(3, 9))
        name = f"inventory_{day:%Y%m%d}.csv" if stype == "csv" else sname
        ing[target] = [dict(
            run_id=f"{pipe}-{day:%Y%m%d}", pipeline_name=pipe,
            activity_name=f"Ingest_{target}", notebook_name=f"nb_{target}",
            trigger_name="TR_Daily_0200", status="Succeeded", error_message=None,
            start_time=fmt(start), end_time=fmt(end),
            rows_written=int(base * rng.uniform(0.95, 1.05)), attempt=1,
            source_type=stype, source_name=name,
            target_type="delta", target_delta_table=target)]
    for i, (script, src, ref, tgt, base) in enumerate(CURATE):
        start = ts(day, 5, 0) + timedelta(minutes=6 * i)
        end = start + timedelta(minutes=rng.randint(1, 5))
        cur[script] = dict(
            run_id=f"CUR-{day:%Y%m%d}", pipeline_name=CUR_PIPELINE,
            script_name=script, status="Succeeded", error_message=None,
            start_time=fmt(start), end_time=fmt(end),
            rows_written=int(base * rng.uniform(0.95, 1.05)),
            source_type="delta", source_name=src, reference_source_name=ref,
            target_type="delta", target_delta_table=tgt)
    return ing, cur


def fail_ing(row, msg, attempt=None):
    row.update(status="Failed", error_message=msg, rows_written=0)
    if attempt:
        row["attempt"] = attempt


def fail_cur(row, msg):
    row.update(status="Failed", error_message=msg, rows_written=0)


def add_retries(attempts, errors):
    """Replace a one-row attempt list with len(errors) failures followed by one success."""
    ok = attempts[0]
    failed = []
    for n, err in enumerate(errors, start=1):
        r = dict(ok)
        r["start_time"] = fmt(datetime.fromisoformat(ok["start_time"]) + timedelta(minutes=15 * (n - 1)))
        r["end_time"] = fmt(datetime.fromisoformat(r["start_time"]) + timedelta(minutes=2))
        fail_ing(r, vary(err, r, salt=n), attempt=n)
        failed.append(r)
    shift = timedelta(minutes=15 * len(errors))
    ok["start_time"] = fmt(datetime.fromisoformat(ok["start_time"]) + shift)
    ok["end_time"] = fmt(datetime.fromisoformat(ok["end_time"]) + shift)
    ok["attempt"] = len(errors) + 1
    attempts[:] = failed + [ok]


# ---------------------------------------------------------------- scenarios
# Each mutator gets (offset, ing, cur); offset 0 = today, 1 = yesterday, and so on.

def scenario_all_healthy(offset, ing, cur):
    pass


def scenario_clean_cascade(offset, ing, cur):
    """CRM ingestion fails. Downstream scripts succeed with 0 new rows (no error anywhere downstream)."""
    if offset != 0:
        return
    row = ing["customer_ingestion"][0]
    fail_ing(row, vary(
        "Operation on target Ingest_customer_ingestion failed: "
        "ErrorCode=SqlFailedToConnect: Login failed for user 'svc_adf_crm'. "
        "Password expired. Activity ID: {guid}", row))
    cur["customer_curation"]["rows_written"] = 0   # succeeded, but nothing new flowed in
    cur["customer_dal"]["rows_written"] = 0
    # sales_curation reads customer_curation as a reference, but its own row count stays normal
    # sales_dal is at risk by transitivity only


def scenario_noisy_recurring(offset, ing, cur):
    """Recovered ingestion retries (noise) plus one script with the same error every day."""
    if offset == 0:
        add_retries(ing["sales_ingestion"], [
            "Operation on target Ingest_sales_ingestion failed: "
            "HttpStatus 429: Too Many Requests from sales_api. Activity ID: {guid}",
            "Operation on target Ingest_sales_ingestion failed: "
            "TimeoutException: request to sales_api/orders timed out after 120s. "
            "Started at {start}"])
    if offset == 2:
        add_retries(ing["sales_ingestion"], [
            "Operation on target Ingest_sales_ingestion failed: "
            "HttpStatus 429: Too Many Requests from sales_api. Activity ID: {guid}"])
    # customer_curation succeeds every day, so the defect is in customer_dal itself
    row = cur["customer_dal"]
    fail_cur(row, vary(
        "AnalysisException: cannot resolve 'segment_code' given input columns "
        "[customer_id, name, city].\n"
        "\tat org.apache.spark.sql.catalyst.analysis.package$AnalysisErrorAt"
        ".failAnalysis(package.scala:54)\n"
        "\tJob run id: {run}, Activity ID: {guid}", row))

def scenario_ambiguous(offset, ing, cur):
    """Sales: empty load plus a curation failure (two plausible causes). Inventory: independent failure."""
    if offset != 0:
        return
    ing["sales_ingestion"][0]["rows_written"] = 0            # succeeded but loaded nothing
    fail_cur(cur["sales_curation"],
             "AnalysisException: cannot resolve 'order_id' given input columns [].")
    cur["sales_dal"]["rows_written"] = 0                     # succeeded, no new rows
    fail_cur(cur["inventory_dal"],
             "AnalysisException: cannot resolve 'reorder_level' given input columns "
             "[item_id, qty, warehouse].")


SCENARIOS = {
    "all_healthy":     (scenario_all_healthy, 11),
    "clean_cascade":   (scenario_clean_cascade, 22),
    "noisy_recurring": (scenario_noisy_recurring, 33),
    "ambiguous":       (scenario_ambiguous, 44),
}

# ---------------------------------------------------------------- expected answers

STATUS_RULE = (
    "Pipeline status rule, applied to today's units (latest attempt per unit): "
    "Failed = at least half of the units ended failed. "
    "Partial = some units failed, but fewer than half. "
    "Degraded = no unit failed, but a unit needed retries, or succeeded with 0 rows when history is normally non-zero. "
    "Healthy = everything succeeded first time with normal row counts."
)

EXPECTED = {
    "all_healthy": dict(
        summary="Nothing is wrong. The tool must not invent problems.",
        incidents="0",
        incident_detail=[],
        statuses={"PL_01_Ingest_Crm": "Healthy", "PL_02_Ingest_Sales": "Healthy",
                  "PL_03_Ingest_Inventory": "Healthy", CUR_PIPELINE: "Healthy (6 of 6 succeeded)"},
        route="status_only (no RCA, no fix proposals)",
    ),
    "clean_cascade": dict(
        summary="One CRM ingestion failure. No downstream script errors, the damage shows as 0 new rows. Inventory must stay clean.",
        incidents="1",
        incident_detail=[
            "Root cause: customer_ingestion failed in PL_01_Ingest_Crm, SQL login failed, password expired for svc_adf_crm. Confidence: high.",
            "Confirmed impacted (succeeded with 0 rows, failed upstream on the lineage): customer_curation, customer_dal.",
            "At risk (read stale customer data through the reference link, own row count normal): sales_curation, then sales_dal by transitivity. Lower confidence.",
            "Not affected: sales_ingestion, every Inventory table. They must NOT appear as victims.",
        ],
        statuses={"PL_01_Ingest_Crm": "Failed", "PL_02_Ingest_Sales": "Healthy",
                  "PL_03_Ingest_Inventory": "Healthy",
                  CUR_PIPELINE: "Degraded (no failures, 2 of 6 scripts wrote 0 rows)"},
        route="cross_layer_rca: ingestion -> curation -> semantic, detect impact by lineage and row-count anomaly, propose the fix at the ingestion root only",
    ),
    "noisy_recurring": dict(
        summary="Recovered ingestion retries (noise) plus one script that fails on its own every day.",
        incidents="1 (customer_dal). The recovered sales_ingestion retries are noise and are not counted.",
        incident_detail=[
            "Root cause: customer_dal references segment_code, which is not in its source customer_curation (columns are customer_id, name, city). Script defect, same error on all 6 days, upstream healthy. Confidence: high.",
            "Victims: none (nothing reads customer_dal).",
            "Noise: sales_ingestion failed twice (HTTP 429, timeout) and succeeded on attempt 3. One earlier 429 retry 2 days ago.",
        ],
        statuses={"PL_01_Ingest_Crm": "Healthy", "PL_02_Ingest_Sales": "Degraded (needed 3 attempts)",
                  "PL_03_Ingest_Inventory": "Healthy",
                  CUR_PIPELINE: "Partial (1 of 6 scripts failed)"},
        route="history_check -> single_layer_triage (semantic only), retries flagged as noise, no cross-layer trace",
    ),
    "ambiguous": dict(
        summary="Sales has two plausible causes and too little evidence. Inventory has a separate, clean failure.",
        incidents="2",
        incident_detail=[
            "Incident A (Sales): root cause undetermined, confidence low. Hypothesis 1: the sales source was empty or its schema changed upstream (sales_ingestion succeeded with 0 rows, normally about 9,800). Hypothesis 2: a defect in sales_curation. Victim: sales_dal (succeeded with 0 rows). Needs a human.",
            "Incident B (Inventory): root cause inventory_dal transformation error (reorder_level not in its source inventory_curation, which succeeded). Confidence: high. Victims: none.",
            "CRM chain is unaffected.",
        ],
        statuses={"PL_01_Ingest_Crm": "Healthy", "PL_02_Ingest_Sales": "Degraded (succeeded with 0 rows, normally about 9,800)",
                  "PL_03_Ingest_Inventory": "Healthy",
                  CUR_PIPELINE: "Partial (2 of 6 scripts failed, sales_dal wrote 0 rows)"},
        route="Incident A: cross_layer_rca -> low confidence -> escalate_to_human with both hypotheses. Incident B: single_layer_triage",
    ),
}


def write_expected(out_dir: Path, today: date):
    lines = ["# CascadeLens expected answers", "",
             f"Run date {today} (today is the latest date in each .db).", "",
             STATUS_RULE, ""]
    for name, e in EXPECTED.items():
        lines += [f"## {name}.db", "", e["summary"], "", f"- Incident count: {e['incidents']}"]
        lines += [f"- {d}" for d in e["incident_detail"]]
        lines.append("- Pipeline statuses:")
        lines += [f"  - {p}: {s}" for p, s in e["statuses"].items()]
        lines += [f"- Route: {e['route']}", ""]
    (out_dir / "expected_answers.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- build

DI_COLS = ["run_id", "pipeline_name", "activity_name", "notebook_name", "trigger_name", "status",
           "error_message", "start_time", "end_time", "rows_written", "attempt", "source_type",
           "source_name", "target_type", "target_delta_table"]
CUR_COLS = ["run_id", "pipeline_name", "script_name", "status", "error_message", "start_time",
            "end_time", "rows_written", "source_type", "source_name", "reference_source_name",
            "target_type", "target_delta_table"]


def insert(conn, table, cols, row):
    conn.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [row[c] for c in cols])


def build(path: Path, mutate, seed: int, today: date):
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    for offset in range(HISTORY_DAYS, -1, -1):
        day = today - timedelta(days=offset)
        ing, cur = baseline_day(day, rng)
        mutate(offset, ing, cur)
        for attempts in ing.values():
            for row in attempts:
                insert(conn, "DiLog", DI_COLS, row)
        for row in cur.values():
            insert(conn, "FwkCurLog", CUR_COLS, row)
    conn.commit()
    return conn


# ---------------------------------------------------------------- checks

def status_board(conn, today: date):
    """Apply the status rule to today's rows so you can compare with expected_answers.md."""
    rows = conn.execute(
        "SELECT pipeline_name, unit_name, status, rows_written, attempt FROM all_logs "
        "WHERE date(start_time) = ? ORDER BY pipeline_name, unit_name, attempt", (str(today),)).fetchall()
    units = {}
    for pipe, unit, status, nrows, attempt in rows:
        units.setdefault(pipe, {})[unit] = (status, nrows, attempt)   # last attempt wins
    board = {}
    for pipe, us in units.items():
        n = len(us)
        failed = sum(1 for s, _, _ in us.values() if s == "Failed")
        retried = any(a > 1 for s, _, a in us.values() if s == "Succeeded")
        zero = sum(1 for s, r, _ in us.values() if s == "Succeeded" and r == 0)
        if failed * 2 >= n:
            st = "Failed"
        elif failed:
            st = "Partial"
        elif retried or zero:
            st = "Degraded"
        else:
            st = "Healthy"
        board[pipe] = f"{st} ({failed} of {n} failed, {zero} with 0 rows{', retried' if retried else ''})"
    return board


def verify_and_print(name, conn, today: date):
    print(f"\n=== {name}.db ===")
    counts = dict(conn.execute("SELECT layer, COUNT(*) FROM all_logs GROUP BY layer"))
    print("  rows by layer:", counts)
    # layer rule check: every _dal script must be semantic, every other script curation
    bad = conn.execute(
        "SELECT unit_name, layer FROM all_logs WHERE layer <> 'ingestion' AND "
        "((unit_name LIKE '%\\_dal%' ESCAPE '\\') <> (layer = 'semantic'))").fetchall()
    assert not bad, f"layer rule broken: {bad}"
    odd = conn.execute(
        "SELECT layer, unit_name, attempt, status, rows_written FROM all_logs "
        "WHERE date(start_time) = ? AND (status <> 'Succeeded' OR rows_written = 0 OR attempt > 1) "
        "ORDER BY start_time", (str(today),)).fetchall()
    print("  today, non-clean rows:", len(odd))
    for r in odd:
        print("   ", r)
    print("  status board (computed):")
    for pipe, st in sorted(status_board(conn, today).items()):
        print(f"    {pipe}: {st}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="run date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=".", help="output folder")
    args = ap.parse_args()
    today = date.fromisoformat(args.date) if args.date else date.today()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for name, (mutate, seed) in SCENARIOS.items():
        conn = build(out / f"{name}.db", mutate, seed, today)
        verify_and_print(name, conn, today)
        conn.close()
    write_expected(out, today)
    print(f"\nWrote {len(SCENARIOS)} .db files and expected_answers.md to {out.resolve()}")


if __name__ == "__main__":
    main()
