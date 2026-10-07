"""Plain Python entry points that compute the facts: statuses, failures and warnings.

No AI is used here. The agents reach these functions through tools.py, and
main.py calls them again after the agents answer to check the agents' facts.
"""
from dataclasses import dataclass
from datetime import date

from cascadelens.error_signature import group_by_signature, make_signature, recurrence_days
from cascadelens.lineage import build_downstream, find_impacted, group_related, split_impacted
from cascadelens.models import LogRecord
from cascadelens.noise_filter import remove_recovered_failures
from cascadelens.reader import read_logs
from cascadelens.pipeline_status import empty_loads, pipeline_statuses
from cascadelens.report import Failure, EmptyLoad


@dataclass(frozen=True)
class Analysis:
    """Result of analyse(), with four named fields.

    Named fields let the tools read result.recurrence instead of guessing the
    position in a tuple.
    """
    today: date
    failure_groups: dict[str, list[LogRecord]]
    recurrence: dict[str, int]
    downstream: dict[str, set[str]]


def analyse(db_path: str) -> Analysis:
    """Read the logs and run the pieces in order.

    Order: read, then the noise filter and grouping on today's rows, recurrence
    on all raw records, and the lineage graph. Statuses are computed separately
    by get_statuses.
    """
    records = read_logs(db_path)
    # "today" is the latest date in the data, not the system date, so old sample databases still work
    today = max(r.start_time for r in records).date()
    todays = [r for r in records if r.start_time.date() == today]
    return Analysis(
        today=today,
        failure_groups=group_by_signature(remove_recovered_failures(todays)),
        recurrence=recurrence_days(records, today),
        downstream=build_downstream(records),
    )


def get_statuses(db_path: str) -> dict[str, str]:
    """Statuses only: the first check in main.py needs nothing more, so it skips the rest of analyse()."""
    records = read_logs(db_path)
    today = max(r.start_time for r in records).date()
    return pipeline_statuses(records, today)


def build_failures(analysis: Analysis, records: list[LogRecord]) -> list[Failure]:
    """Build one Failure per independent failure group, using only plain Python.

    Args:
    - analysis: the result of analyse(db_path)
    - records: the raw LogRecord rows, needed by split_impacted
    Returns: a list of Failure, sorted by failed table name.
    """
    # keep one example record per failed table, its error text becomes the root cause
    first_record = {}
    for group in analysis.failure_groups.values():
        for record in group:
            first_record.setdefault(record.target_delta_table, record)

    failures = []
    # each group is a set of failed tables linked by lineage, so it is one cascade
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
                # raw error text here, the agent turns it into a plain sentence
                root_cause=record.error_message or "Unknown error",
                recurrence_days=analysis.recurrence.get(make_signature(record.error_message), 0),
                confirmed_impacted=sorted(confirmed),
                at_risk=sorted(at_risk),
            )
        )
    return sorted(failures, key=lambda f: f.failed_table)


def build_warnings(analysis: Analysis, records: list[LogRecord], failures: list[Failure]) -> list[EmptyLoad]:
    """Build one EmptyLoad warning per empty load that is not already explained by a failure.

    A table is skipped when it is a failed table or a confirmed victim.
    Returns: a list of EmptyLoad, sorted by empty table name.
    """
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
