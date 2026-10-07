"""Table lineage: which tables sit below a failed table, and which of them are hit.

Plain Python, no AI. A table depends on another when it reads it as a source
or as a reference.
"""
from collections import defaultdict
from datetime import date

from cascadelens.models import LogRecord
from cascadelens.pipeline_status import is_normally_non_zero, latest_attempts


def build_downstream(records: list[LogRecord]) -> dict[str, set[str]]:
    """Build the lineage graph: for each source table, the tables that read it directly.

    Why: when customer_ingestion fails, we need to know which units sit
    downstream of it. This is what separates the real victims from the
    inventory chain, which must never appear as a victim.
    """
    downstream = defaultdict(set)
    for record in records:
        # ingestion rows read an external system, not a table, so they add no edges
        if record.layer == "ingestion":
            continue
        # reference_source_name is a second input, such as Sales reading customer_curation
        for source in (record.source_name, record.reference_source_name):
            if source:
                downstream[source].add(record.target_delta_table)
    return dict(downstream)


def find_impacted(downstream: dict[str, set[str]], failed_table: str) -> set[str]:
    """Trace everything downstream of a failed table.

    Why: build_downstream only gives direct children. If customer_ingestion
    fails, we also need the grandchildren: customer_curation, then customer_dal
    and sales_curation, then sales_dal. The tracing walks the graph until
    nothing new turns up.

    Args:
    - downstream: the graph of direct children, as built by build_downstream
    - failed_table: the table that failed, which is the root of the tracing
    Returns: the set of all downstream tables, including direct children and
    grandchildren, etc. The failed_table itself is not included.
    """
    impacted = set()
    todo = [failed_table]
    while todo:
        table = todo.pop()
        for child in downstream.get(table, set()):
            if child not in impacted:
                impacted.add(child)
                todo.append(child)
    return impacted


def split_impacted(
    records: list[LogRecord], impacted: set[str], day: date
) -> tuple[set[str], set[str]]:
    """Split the impacted tables into two kinds of victim.

    Confirmed impacted: downstream units that succeeded today with 0 rows, while
    their history is normally non-zero (customer_curation and customer_dal in
    clean_cascade).
    At risk: downstream units that did not show 0 rows, but sit below the failure
    (sales_curation and sales_dal).

    impacted - confirmed is set subtraction: everything impacted that was not
    confirmed. A unit that never ran today is not in latest_attempts, so it lands
    in "at risk". That is a deliberate simplification, and a future "Not run"
    status would treat it separately.

    Args:
    - records: the raw LogRecord rows, not filtered by day or status.
    - impacted: the set of all downstream tables, as built by find_impacted
    - day: the day to consider as "today".
    Returns: a tuple of two sets, (confirmed, at_risk).
    """
    confirmed = set()
    for key, record in latest_attempts(records, day).items():
        if record.target_delta_table not in impacted:
            continue
        if not record.is_failed and (record.rows_written or 0) == 0:
            if is_normally_non_zero(records, key, day):
                confirmed.add(record.target_delta_table)
    return confirmed, impacted - confirmed


def group_related(
    downstream: dict[str, set[str]], failed_tables: set[str]
) -> list[set[str]]:
    """Group failed tables that are connected by lineage.

    Two failed tables are related when one sits downstream of the other.

    Args:
    - downstream: the graph of direct children, as built by build_downstream
    - failed_tables: the set of tables that failed today
    Returns: a list of sets, one set per independent failure. Order follows the
    sorted table names.
    """
    groups: list[set[str]] = []
    for table in sorted(failed_tables):
        below = find_impacted(downstream, table)
        merged = {table}
        # merge every existing group that is linked to this table in either direction
        for group in list(groups):
            if any(other in below or table in find_impacted(downstream, other) for other in group):
                merged |= group
                groups.remove(group)
        groups.append(merged)
    return groups
