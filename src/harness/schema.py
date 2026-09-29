import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    primary_key: bool


@dataclass(frozen=True)
class ForeignKeyInfo:
    column: str
    referenced_table: str
    referenced_column: str | None


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[ColumnInfo, ...]
    foreign_keys: tuple[ForeignKeyInfo, ...]


@dataclass(frozen=True)
class DatabaseSchema:
    tables: tuple[TableSchema, ...]

    def to_prompt(self) -> str:
        """
        Convert database metadata into a deterministic
        text representation for the LLM prompt.
        """

        lines: list[str] = [
            "DATABASE SCHEMA",
            "",
        ]

        for table in self.tables:
            lines.append(f"Table: {table.name}")
            lines.append("Columns:")

            for column in table.columns:
                attributes: list[str] = []

                if column.primary_key:
                    attributes.append("PRIMARY KEY")

                if not column.nullable:
                    attributes.append("NOT NULL")

                suffix = ""

                if attributes:
                    suffix = " " + " ".join(attributes)

                data_type = column.data_type or "UNKNOWN"

                lines.append(
                    f"- {column.name} {data_type}{suffix}"
                )

            if table.foreign_keys:
                lines.append("Foreign Keys:")

                for foreign_key in table.foreign_keys:
                    referenced_column = (
                        foreign_key.referenced_column
                        or "<implicit>"
                    )

                    lines.append(
                        f"- {foreign_key.column} -> "
                        f"{foreign_key.referenced_table}."
                        f"{referenced_column}"
                    )

            lines.append("")

        return "\n".join(lines).strip()


class SQLiteSchemaInspector:
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

        return sqlite3.connect(
            uri,
            uri=True,
        )

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Escape SQLite identifiers before using them
        inside PRAGMA statements.
        """

        escaped = identifier.replace('"', '""')

        return f'"{escaped}"'

    def _get_table_names(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[str, ...]:

        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        return tuple(row[0] for row in rows)

    def _get_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
    ) -> tuple[ColumnInfo, ...]:

        quoted_table = self._quote_identifier(table_name)

        rows = connection.execute(
            f"PRAGMA table_info({quoted_table})"
        ).fetchall()

        columns: list[ColumnInfo] = []

        for row in rows:
            _, name, data_type, not_null, _, primary_key = row

            is_primary_key = bool(primary_key)

            columns.append(
                ColumnInfo(
                    name=name,
                    data_type=data_type,
                    nullable=not bool(
                        not_null or is_primary_key
                    ),
                    primary_key=is_primary_key,
                )
            )

        return tuple(columns)

    def _get_foreign_keys(
        self,
        connection: sqlite3.Connection,
        table_name: str,
    ) -> tuple[ForeignKeyInfo, ...]:

        quoted_table = self._quote_identifier(table_name)

        rows = connection.execute(
            f"PRAGMA foreign_key_list({quoted_table})"
        ).fetchall()

        foreign_keys: list[ForeignKeyInfo] = []

        for row in rows:
            referenced_table = row[2]
            column = row[3]
            referenced_column = row[4]

            foreign_keys.append(
                ForeignKeyInfo(
                    column=column,
                    referenced_table=referenced_table,
                    referenced_column=referenced_column,
                )
            )

        return tuple(foreign_keys)

    def inspect(self) -> DatabaseSchema:
        with self._connect() as connection:
            table_names = self._get_table_names(
                connection
            )

            tables: list[TableSchema] = []

            for table_name in table_names:
                tables.append(
                    TableSchema(
                        name=table_name,
                        columns=self._get_columns(
                            connection,
                            table_name,
                        ),
                        foreign_keys=self._get_foreign_keys(
                            connection,
                            table_name,
                        ),
                    )
                )

        return DatabaseSchema(
            tables=tuple(tables)
        )