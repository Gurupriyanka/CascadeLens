from cascadelens.models import LogRecord


def remove_recovered_failures(records: list[LogRecord]) -> list[LogRecord]:
    # Pass 1: for each (run_id, unit_name), find the attempt number that succeeded
    success_attempt = {}
    for r in records:
        if r.status == "Succeeded" and r.attempt is not None:
            key = (r.run_id, r.unit_name)
            success_attempt[key] = max(success_attempt.get(key, 0), r.attempt)

    # Pass 2: keep every record except failures that a later attempt recovered
    kept = []
    for r in records:
        key = (r.run_id, r.unit_name)
        recovered = (
            r.is_failed
            and r.attempt is not None
            and success_attempt.get(key, 0) > r.attempt
        )
        if not recovered:
            kept.append(r)
    return kept