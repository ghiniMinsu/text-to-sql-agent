import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)


class SQLiteReadOnlyExecutor:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()

        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database file not found: {self.db_path}"
            )

        if not self.db_path.is_file():
            raise ValueError(
                f"Database path is not a file: {self.db_path}"
            )

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self.db_path.as_uri()}?mode=ro"

        connection = sqlite3.connect(
            uri,
            uri=True,
        )

        connection.execute("PRAGMA query_only = ON")

        return connection

    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> QueryResult:
        with self._connect() as connection:
            cursor = connection.execute(sql, parameters)

            rows = tuple(
                tuple(row)
                for row in cursor.fetchall()
            )

            if cursor.description is None:
                columns: tuple[str, ...] = ()
            else:
                columns = tuple(
                    description[0]
                    for description in cursor.description
                )

            return QueryResult(
                columns=columns,
                rows=rows,
            )
