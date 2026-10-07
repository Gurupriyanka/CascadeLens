import sqlite3
from contextlib import closing
from pathlib import Path

from cascadelens.models import LogRecord


def read_logs(db_path: str | Path) -> list[LogRecord]:
    """Read every row of the all_logs view of a SQLite database.

    Args:
        db_path: path to the SQLite file.

    Returns:
        One LogRecord per row.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the database has no usable all_logs view.
    """
    path = Path(db_path)
    # Check first, because sqlite3.connect would silently create an empty file.
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")

    # closing() makes sure the connection is closed after reading.
    with closing(sqlite3.connect(path)) as conn:
        # Row access by column name, which LogRecord.from_row relies on.
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM all_logs").fetchall()
        except sqlite3.OperationalError as e:
            raise ValueError(f"{path} has no usable all_logs view: {e}") from e

    return [LogRecord.from_row(r) for r in rows]
