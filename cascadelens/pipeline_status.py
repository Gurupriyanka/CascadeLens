from datetime import date

from cascadelens.models import LogRecord


def latest_attempts(
    records: list[LogRecord], day: date
) -> dict[tuple[str, str], LogRecord]:
    """Return the latest attempt of each unit on the given day.

    Records are keyed by (pipeline_name, unit_name) and processed in time
    order, so a later record overwrites an earlier one with the same key.
    """
    latest = {}
    todays = [r for r in records if r.start_time.date() == day]
    # Sorted by start_time, so the last write per key is the latest attempt.
    for record in sorted(todays, key=lambda r: r.start_time):
        latest[(record.pipeline_name, record.unit_name)] = record
    return latest


# The four pipeline statuses, from worst to best.
FAILED = "Failed"
PARTIALLY_FAILED = "Partially Failed"
SUCCEEDED_WITH_ISSUES = "Succeeded with Issues"
HEALTHY = "Healthy"


def status_from_counts(
    total_units: int, failed_units: int, retried_units: int, zero_row_units: int
) -> str:
    """Turn the four unit counts of a pipeline into one status (pure function).

    The decision ladder, first match wins. The order matters: Failed is
    checked first, then Partially Failed, and only a pipeline with no failures
    can be Succeeded with Issues.

    failed_units * 2 >= total_units means "at least half" without division.
    Raises ValueError for a pipeline with 0 units, because 0 failed of 0 units
    would otherwise return Failed. A pipeline that did not run at all is the
    future "Not run" detection, so it is deliberately not handled here.

    status_from_counts(6, 1, 0, 0)   # "Partially Failed"
    status_from_counts(6, 3, 0, 0)   # "Failed" (exactly half counts as Failed)
    """
    if total_units == 0:
        raise ValueError("a pipeline with no units has no status")
    if failed_units * 2 >= total_units:
        return FAILED
    if failed_units > 0:
        return PARTIALLY_FAILED
    if retried_units > 0 or zero_row_units > 0:
        return SUCCEEDED_WITH_ISSUES
    return HEALTHY


def pipeline_statuses(records: list[LogRecord], day: date) -> dict[str, str]:
    """Return the status of each pipeline that ran on the given day.

    Computes the four counts for each pipeline from the latest attempts, then
    applies the ladder in status_from_counts. A unit counts as retried when it
    succeeded with attempt > 1. A missing attempt is treated as 1.
    """
    # Group the latest attempts by pipeline.
    units_by_pipeline = {}
    for (pipeline, _unit), record in latest_attempts(records, day).items():
        units_by_pipeline.setdefault(pipeline, []).append(record)

    statuses = {}
    for pipeline, units in units_by_pipeline.items():
        failed = 0
        retried = 0
        zero_rows = 0
        for unit in units:
            if unit.is_failed:
                failed += 1
            else:
                # Retries and empty loads only matter for units that succeeded.
                if (unit.attempt or 1) > 1:
                    retried += 1
                key = (unit.pipeline_name, unit.unit_name)
                if unit.rows_written == 0 and is_normally_non_zero(records, key, day):
                    zero_rows += 1
        statuses[pipeline] = status_from_counts(len(units), failed, retried, zero_rows)
    return statuses


def is_normally_non_zero(
    records: list[LogRecord], unit_key: tuple[str, str], day: date
) -> bool:
    """Tell whether a unit normally writes rows, judged by its earlier runs.

    Only successful runs before the given day count as history. The unit
    normally writes rows when more than half of that history wrote rows.

    Args:
        records: the raw LogRecord rows, not filtered by day or status.
        unit_key: a tuple of (pipeline_name, unit_name) to identify the unit.
        day: the day to consider as "today" for the window.

    Returns:
        True if the unit has a history of writing non-zero rows, False otherwise.
    """
    history = [
        r for r in records
        if (r.pipeline_name, r.unit_name) == unit_key
        and r.start_time.date() < day
        and not r.is_failed
    ]
    # No history means we cannot say the unit normally writes rows.
    if not history:
        return False
    # "More than half" written as a multiplication, so no division is needed.
    return sum((r.rows_written or 0) > 0 for r in history) * 2 > len(history)


def empty_loads(records: list[LogRecord], day: date) -> dict[str, str]:
    """Find units that succeeded today with 0 rows although they normally write rows.

    Retried units are not included, because a retry has no downstream victims.

    Returns:
        A dict mapping the target table to the pipeline that ran it.
    """
    found = {}
    for key, record in latest_attempts(records, day).items():
        if not record.is_failed and record.rows_written == 0 and is_normally_non_zero(records, key, day):
            found[record.target_delta_table] = record.pipeline_name
    return found
