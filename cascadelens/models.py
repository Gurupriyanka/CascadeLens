"""LogRecord: one row of the unified all_logs view."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LogRecord:
    """One log row from any layer (ingestion, curation or semantic).

    Frozen, so a record cannot change after it is read. Most fields are optional
    because the layers do not fill the same columns.
    """
    layer: str
    log_id: int
    run_id: str | None = None
    pipeline_name: str | None = None
    unit_name: str | None = None
    notebook_name: str | None = None
    trigger_name: str | None = None
    status: str | None = None
    error_message: str | None = None  # NULL for successful rows
    start_time: datetime | None = None
    end_time: datetime | None = None
    rows_written: int | None = None
    attempt: int | None = None  # 1 is the first try, higher means a retry; may be missing
    source_type: str | None = None
    source_name: str | None = None
    reference_source_name: str | None = None  # a second input table, if any
    target_type: str | None = None
    target_delta_table: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LogRecord":
        """Build a record from a database row. Times are stored as ISO text, so convert them."""
        data = dict(row)
        data["start_time"] = datetime.fromisoformat(data["start_time"]) if data["start_time"] else None
        data["end_time"] = datetime.fromisoformat(data["end_time"]) if data["end_time"] else None
        return cls(**data)

    @property
    def is_failed(self) -> bool:
        """True when this attempt ended with status Failed."""
        return self.status == "Failed"
