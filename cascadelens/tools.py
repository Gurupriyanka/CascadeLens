import json

from smolagents import tool

from cascadelens.analysis import analyse
from cascadelens.lineage import build_downstream, find_impacted
from cascadelens.reader import read_logs
from cascadelens.lineage import build_downstream, find_impacted, split_impacted


@tool
def get_pipeline_statuses(db_path: str) -> str:
    """Return the health status of each pipeline for the latest day in a log database.

    Args:
        db_path: Path to the SQLite log database to analyse.
    """
    result = analyse(db_path)
    return json.dumps(result.statuses)


@tool
def get_failure_groups(db_path: str) -> str:
    """Return today's failures grouped by error signature, with how many days each one has recurred.

    Args:
        db_path: Path to the SQLite log database to analyse.
    """
    result = analyse(db_path)
    groups = []
    for signature, records in result.failure_groups.items():
        groups.append(
            {
                "signature": signature,
                "recurrence_days": result.recurrence.get(signature, 0),
                "layers": sorted({r.layer for r in records}),
                "failed_units": sorted({r.unit_name for r in records if r.unit_name}),
                "target_tables": sorted({r.target_delta_table for r in records if r.target_delta_table}),
                "example_error": records[0].error_message,
            }
        )
    return json.dumps(groups)

@tool
def get_impacted_tables(db_path: str, failed_table: str) -> str:
    """Return every table downstream of a failed table, found by walking the lineage graph.

    Args:
        db_path: Path to the SQLite log database to analyse.
        failed_table: Name of the table that failed, for example customer_ingestion.
    """
    records = read_logs(db_path)
    downstream = build_downstream(records)
    impacted = find_impacted(downstream, failed_table)
    return json.dumps(sorted(impacted))

@tool
def split_impacted_tables(db_path: str, impacted_tables: list[str]) -> str:
    """Split a list of impacted tables into confirmed impact and at risk.

    Call this after get_impacted_tables, passing its result unchanged as impacted_tables.
    Confirmed means the table ran today but wrote 0 rows although it normally writes rows.
    At risk means every other table in the list.

    Args:
        db_path: Path to the SQLite log database to analyse.
        impacted_tables: The list of table names returned by get_impacted_tables.
    """
    records = read_logs(db_path)
    today = analyse(db_path).today
    confirmed, at_risk = split_impacted(records, set(impacted_tables), today)
    return json.dumps({"confirmed": sorted(confirmed), "at_risk": sorted(at_risk)})