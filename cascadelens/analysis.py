from dataclasses import dataclass
from datetime import date

from cascadelens.error_signature import group_by_signature, recurrence_days
from cascadelens.lineage import build_downstream
from cascadelens.models import LogRecord
from cascadelens.noise_filter import remove_recovered_failures
from cascadelens.pipeline_status import pipeline_statuses
from cascadelens.reader import read_logs


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