from cascadelens.models import LogRecord


def test_failed_status_is_detected():
    record = LogRecord(layer="ingestion", log_id=1, status="Failed")
    assert record.is_failed is True