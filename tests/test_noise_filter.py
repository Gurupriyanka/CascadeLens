from cascadelens.models import LogRecord
from cascadelens.noise_filter import remove_recovered_failures


def test_failure_recovered_by_retry_is_removed():
    failed = LogRecord(
        layer="ingestion", log_id=11, run_id="RUN-1",
        unit_name="Ingest_sales", status="Failed", attempt=1,
    )
    retry = LogRecord(
        layer="ingestion", log_id=12, run_id="RUN-1",
        unit_name="Ingest_sales", status="Succeeded", attempt=2,
    )

    result = remove_recovered_failures([failed, retry])

    assert result == [retry]

def test_success_before_the_failure_does_not_recover_it():
    # attempt 1 succeeded, then attempt 2 failed: the failure is NOT recovered
    success = LogRecord(
        layer="ingestion", log_id=1, run_id="RUN-1",
        unit_name="Ingest_sales", status="Succeeded", attempt=1,
    )
    failed = LogRecord(
        layer="ingestion", log_id=2, run_id="RUN-1",
        unit_name="Ingest_sales", status="Failed", attempt=2,
    )

    result = remove_recovered_failures([success, failed])

    assert result == [success, failed]


def test_success_in_a_different_run_does_not_recover_the_failure():
    # RUN-1 failed, and only RUN-2 (a different run) succeeded
    failed = LogRecord(
        layer="ingestion", log_id=1, run_id="RUN-1",
        unit_name="Ingest_sales", status="Failed", attempt=1,
    )
    other_run_success = LogRecord(
        layer="ingestion", log_id=2, run_id="RUN-2",
        unit_name="Ingest_sales", status="Succeeded", attempt=2,
    )

    result = remove_recovered_failures([failed, other_run_success])

    assert result == [failed, other_run_success]

def test_failure_that_never_recovers_is_kept():
    # same unit fails on two different days, no success in either run
    day1 = LogRecord(
        layer="semantic", log_id=4, run_id="CUR-20260925",
        unit_name="customer_dal", status="Failed", attempt=1,
    )
    day2 = LogRecord(
        layer="semantic", log_id=10, run_id="CUR-20260926",
        unit_name="customer_dal", status="Failed", attempt=1,
    )

    result = remove_recovered_failures([day1, day2])

    assert result == [day1, day2]