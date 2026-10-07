from cascadelens.models import LogRecord


def remove_recovered_failures(records: list[LogRecord]) -> list[LogRecord]:
    """Drop failed attempts that a later attempt of the same unit recovered.

    A unit is identified by (run_id, unit_name). A failure is removed only when
    a higher attempt number of that unit succeeded. Failures with no later
    success are kept, so real failures stay visible.

    Returns:
        The records without the recovered failures, in their original order.
    """
    # Pass 1: for each (run_id, unit_name), find the highest attempt number that succeeded.
    success_attempt = {}
    for r in records:
        if r.status == "Succeeded" and r.attempt is not None:
            key = (r.run_id, r.unit_name)
            success_attempt[key] = max(success_attempt.get(key, 0), r.attempt)

    # Pass 2: keep every record except failures that a later attempt recovered.
    kept = []
    for r in records:
        key = (r.run_id, r.unit_name)
        # Recovered means: failed, has an attempt number, and a higher attempt succeeded.
        recovered = (
            r.is_failed
            and r.attempt is not None
            and success_attempt.get(key, 0) > r.attempt
        )
        if not recovered:
            kept.append(r)
    return kept
