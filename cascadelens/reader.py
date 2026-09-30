import sqlite3
from pathlib import Path
from typing import Optional
from .models import LogRecord, Layer, RunStatus

def _map_status(raw: str) -> RunStatus:
    raw = (raw or "").strip().lower()
    if raw in ("succeeded", "success", "completed"):
        return RunStatus.SUCCESS
    if raw in ("failed", "failure", "error"):
        return RunStatus.FAILED
    return RunStatus.OTHER

def read_logs(db_path: str, since: Optional[str] = None) -> list[LogRecord]:
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Log database not found: {path}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM all_logs"
        params = ()
        if since:
            sql += " WHERE start_time >= ?"
            params = (since,)
        sql += " ORDER BY start_time"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [
        LogRecord(
            layer=Layer(r["layer"]),
            pipeline_name=r["pipeline_name"],
            object_name=r["object_name"],
            status=_map_status(r["status"]),
            start_time=r["start_time"],
            end_time=r["end_time"],
            error_message=r["error_message"],
            rows_written=r["rows_written"],
            source_type=r["source_type"],
            source_name=r["source_name"],
            target_type=r["target_type"],
            target_table=r["target_table"],
        )
        for r in rows
    ]