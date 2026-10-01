from datetime import date, datetime

import pytest

from cascadelens.models import LogRecord
from cascadelens.pipeline_status import is_normally_non_zero, latest_attempts, pipeline_statuses, status_from_counts


def attempt(log_id, pipeline, unit, status, day, hour, minute):
    return LogRecord(
        layer="ingestion",
        log_id=log_id,
        pipeline_name=pipeline,
        unit_name=unit,
        status=status,
        start_time=datetime(day.year, day.month, day.day, hour, minute),
    )


def test_latest_attempt_of_today_wins_per_unit():
    today = date(2026, 10, 1)
    yesterday = date(2026, 9, 30)
    records = [
        attempt(1, "PL_02", "Ingest_sales", "Failed", today, 2, 10),
        attempt(2, "PL_02", "Ingest_sales", "Succeeded", today, 2, 40),
        attempt(3, "PL_02", "Ingest_sales", "Failed", yesterday, 2, 10),
        attempt(4, "PL_03", "Ingest_sales", "Failed", today, 2, 20),
    ]

    latest = latest_attempts(records, today)

    assert latest[("PL_02", "Ingest_sales")].status == "Succeeded"
    assert latest[("PL_03", "Ingest_sales")].status == "Failed"
    assert len(latest) == 2

@pytest.mark.parametrize(
    "total, failed, retried, zero_rows, expected",
    [
        (6, 0, 0, 0, "Healthy"),
        (6, 1, 0, 0, "Partially Failed"),
        (6, 3, 0, 0, "Failed"),      # exactly half counts as Failed
        (3, 3, 0, 0, "Failed"),
        (1, 0, 1, 0, "Succeeded with Issues"),    # needed retries
        (6, 0, 0, 2, "Succeeded with Issues"),    # succeeded with 0 rows
        (6, 1, 1, 1, "Partially Failed"),     # a failure outranks Degraded
    ],
)
def test_status_rule(total, failed, retried, zero_rows, expected):
    assert status_from_counts(total, failed, retried, zero_rows) == expected


def test_pipeline_with_no_units_is_an_error():
    with pytest.raises(ValueError):
        status_from_counts(0, 0, 0, 0)

def unit_row(log_id, pipeline, unit, status, attempt, rows, hour, minute):
    return LogRecord(
        layer="ingestion",
        log_id=log_id,
        pipeline_name=pipeline,
        unit_name=unit,
        status=status,
        attempt=attempt,
        rows_written=rows,
        start_time=datetime(2026, 10, 1, hour, minute),
    )


def test_pipeline_statuses_from_records():
    today = date(2026, 10, 1)
    records = [
        # PL_A: two attempts, the second succeeded after a retry
        unit_row(1, "PL_A", "u1", "Failed", 1, 0, 2, 0),
        unit_row(2, "PL_A", "u1", "Succeeded", 2, 100, 2, 15),
        # PL_B: one unit failed, one fine
        unit_row(3, "PL_B", "u1", "Failed", 1, 0, 5, 0),
        unit_row(4, "PL_B", "u2", "Succeeded", 1, 50, 5, 10),
        unit_row(5, "PL_B", "u3", "Succeeded", 1, 60, 5, 20),
        # PL_C: everything normal
        unit_row(6, "PL_C", "u1", "Succeeded", 1, 70, 6, 0),
    ]

    assert pipeline_statuses(records, today) == {
        "PL_A": "Succeeded with Issues",
        "PL_B": "Partially Failed",
        "PL_C": "Healthy",
    }

def test_zero_rows_count_only_when_history_is_normally_non_zero():
    today = date(2026, 10, 1)

    def row(log_id, unit, day, rows):
        return LogRecord(
            layer="ingestion", log_id=log_id, pipeline_name="PL_A", unit_name=unit,
            status="Succeeded", attempt=1, rows_written=rows,
            start_time=datetime(day.year, day.month, day.day, 2, 0),
        )

    records = [
        row(1, "busy", date(2026, 9, 29), 100),
        row(2, "busy", date(2026, 9, 30), 120),
        row(3, "busy", today, 0),
        row(4, "quiet", date(2026, 9, 29), 0),
        row(5, "quiet", date(2026, 9, 30), 0),
        row(6, "quiet", today, 0),
    ]

    assert is_normally_non_zero(records, ("PL_A", "busy"), today) is True
    assert is_normally_non_zero(records, ("PL_A", "quiet"), today) is False
    assert pipeline_statuses(records, today) == {"PL_A": "Succeeded with Issues"}

def test_missing_attempt_and_rows_do_not_crash():
    today = date(2026, 10, 1)

    def row(log_id, day, hour):
        return LogRecord(
            layer="curation", log_id=log_id, pipeline_name="PL_A", unit_name="u1",
            status="Succeeded", attempt=None, rows_written=None,
            start_time=datetime(day.year, day.month, day.day, hour, 0),
        )

    records = [row(1, date(2026, 9, 30), 5), row(2, today, 5)]

    assert pipeline_statuses(records, today) == {"PL_A": "Healthy"}