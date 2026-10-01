from collections import defaultdict

from cascadelens.models import LogRecord

from datetime import date

from cascadelens.pipeline_status import is_normally_non_zero, latest_attempts

# lineage graph, the downstream dependencies
# Why: when customer_ingestion fails, we need to know which units sit downstream of it. This is what separates the real victims from the inventory chain, which must never appear as a victim.
def build_downstream(records: list[LogRecord]) -> dict[str, set[str]]:
    downstream = defaultdict(set)
    for record in records:
        if record.layer == "ingestion":
            continue
        for source in (record.source_name, record.reference_source_name):
            if source:
                downstream[source].add(record.target_delta_table)
    return dict(downstream)

# impact tracing (everything downstream of a failed table)
# Why: build_downstream only gives direct children. If customer_ingestion fails, we also need the grandchildren, so customer_curation, then customer_dal and sales_curation, then sales_dal. The tracing walks the graph until nothing new turns up.
def find_impacted(downstream: dict[str, set[str]], failed_table: str) -> set[str]:
    impacted = set()
    todo = [failed_table]
    while todo:
        table = todo.pop()
        for child in downstream.get(table, set()):
            if child not in impacted:
                impacted.add(child)
                todo.append(child)
    return impacted

# two kinds of victim, and find_impacted does not separate them yet:

# Confirmed impacted: downstream units that succeeded today with 0 rows, while their history is normally non-zero. (customer_curation and customer_dal in clean_cascade.)
# At risk: downstream units that did not show 0 rows, but sit below the failure. (sales_curation and sales_dal.)
# impacted - confirmed is set subtraction: everything impacted that was not confirmed. A unit that never ran today is not in latest_attempts, so it lands in "at risk". That is a deliberate simplification, and it ties to your future "Not run" idea.
def split_impacted(
    records: list[LogRecord], impacted: set[str], day: date
) -> tuple[set[str], set[str]]:
    confirmed = set()
    for key, record in latest_attempts(records, day).items():
        if record.target_delta_table not in impacted:
            continue
        if not record.is_failed and (record.rows_written or 0) == 0:
            if is_normally_non_zero(records, key, day):
                confirmed.add(record.target_delta_table)
    return confirmed, impacted - confirmed

