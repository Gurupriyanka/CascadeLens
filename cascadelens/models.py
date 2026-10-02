from datetime import datetime
import sqlite3
from dataclasses import dataclass

@dataclass(frozen=True)
class LogRecord:
    layer: str
    log_id: int
    run_id: str | None = None
    pipeline_name: str | None = None
    unit_name: str | None = None
    notebook_name: str | None = None
    trigger_name: str | None = None
    status: str | None = None
    error_message: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    rows_written: int | None = None
    attempt: int | None = None
    source_type: str | None = None
    source_name: str | None = None
    reference_source_name: str | None = None
    target_type: str | None = None
    target_delta_table: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "LogRecord":
        data = dict(row)
        data["start_time"] = datetime.fromisoformat(data["start_time"]) if data["start_time"] else None
        data["end_time"] = datetime.fromisoformat(data["end_time"]) if data["end_time"] else None
        return cls(**data)

    @property
    def is_failed(self) -> bool:
        return self.status == "Failed"
