from dataclasses import dataclass
from datetime import date

from cascadelens.error_signature import group_by_signature, make_signature, recurrence_days
from cascadelens.lineage import build_downstream, find_impacted, group_related, split_impacted
from cascadelens.models import LogRecord
from cascadelens.noise_filter import remove_recovered_failures
from cascadelens.reader import read_logs
from cascadelens.pipeline_status import empty_loads, pipeline_statuses
from cascadelens.report import Failure, EmptyLoad


#Analysis is a container with five named fields, so the agent later reads result.statuses instead of guessing the position in a tuple.
#analyse runs the pieces in the agreed order: read, statuses, then the noise filter and grouping on today's rows, recurrence on all raw records, and the lineage graph.

@dataclass(frozen=True)
class Analysis:
    today: date
    statuses: dict[str, str]
    failure_groups: dict[str, list[LogRecord]]
    recurrence: dict[str, int]
    downstream: dict[str, set[str]]


def analyse(db_path: str) -> Analysis:
    records = read_logs(db_path)
    today = max(r.start_time for r in records).date()
    todays = [r for r in records if r.start_time.date() == today]
    return Analysis(
        today=today,
        statuses=pipeline_statuses(records, today),
        failure_groups=group_by_signature(remove_recovered_failures(todays)),
        recurrence=recurrence_days(records, today),
        downstream=build_downstream(records),
    )


# Build one Failure per independent failure group, using only plain Python.
# Args:
# - analysis: the result of analyse(db_path)
# - records: the raw LogRecord rows, needed by split_impacted
# Returns: a list of Failure, sorted by failed table name.
def build_failures(analysis: Analysis, records: list[LogRecord]) -> list[Failure]:
    first_record = {}
    for group in analysis.failure_groups.values():
        for record in group:
            first_record.setdefault(record.target_delta_table, record)

    failures = []
    for tables in group_related(analysis.downstream, set(first_record)):
        # the root is the failed table that is not below any other failed table in the group
        roots = [
            t for t in sorted(tables)
            if not any(t in find_impacted(analysis.downstream, o) for o in tables if o != t)
        ]
        root = roots[0]
        record = first_record[root]
        impacted = find_impacted(analysis.downstream, root)
        confirmed, at_risk = split_impacted(records, impacted, analysis.today)
        failures.append(
            Failure(
                failed_table=root,
                root_cause=record.error_message or "Unknown error",
                recurrence_days=analysis.recurrence.get(make_signature(record.error_message), 0),
                confirmed_impacted=sorted(confirmed),
                at_risk=sorted(at_risk),
            )
        )
    return sorted(failures, key=lambda f: f.failed_table)


# Build one Warning per empty load that is not already a confirmed victim of a failure.
# Returns: a list of Warning, sorted by empty table name.
def build_warnings(analysis: Analysis, records: list[LogRecord], failures: list[Failure]) -> list[EmptyLoad]:
    already_listed = {t for f in failures for t in f.confirmed_impacted} | {f.failed_table for f in failures}
    warnings = []
    for table, pipeline in sorted(empty_loads(records, analysis.today).items()):
        if table in already_listed:
            continue
        warnings.append(
            EmptyLoad(
                pipeline=pipeline,
                empty_table=table,
                at_risk=sorted(find_impacted(analysis.downstream, table)),
            )
        )
    return warnings