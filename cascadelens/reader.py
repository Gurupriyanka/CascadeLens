import sqlite3
from contextlib import closing
from pathlib import Path

from cascadelens.models import LogRecord


def read_logs(db_path: str | Path) -> list[LogRecord]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM all_logs").fetchall()
        except sqlite3.OperationalError as e:
            raise ValueError(f"{path} has no usable all_logs view: {e}") from e

    return [LogRecord.from_row(r) for r in rows]