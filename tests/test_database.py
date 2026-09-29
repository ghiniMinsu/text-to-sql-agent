import sqlite3

import pytest

from src.harness.database import SQLiteReadOnlyExecutor


@pytest.fixture
def sample_db(tmp_path):
    db_path = tmp_path / "sample.db"

    connection = sqlite3.connect(db_path)

    connection.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    connection.execute(
        "INSERT INTO users (name) VALUES (?)",
        ("Alice",),
    )

    connection.commit()
    connection.close()

    return db_path


def test_select_query(sample_db):
    db = SQLiteReadOnlyExecutor(sample_db)

    result = db.execute("""
        SELECT id, name
        FROM users
    """)

    assert result.columns == ("id", "name")
    assert result.rows == ((1, "Alice"),)
    assert result.row_count == 1


def test_write_query_is_blocked(sample_db):
    db = SQLiteReadOnlyExecutor(sample_db)

    with pytest.raises(sqlite3.OperationalError):
        db.execute("""
            DELETE FROM users
        """)


def test_missing_database():
    with pytest.raises(FileNotFoundError):
        SQLiteReadOnlyExecutor(
            "database-that-does-not-exist.db"
        )
