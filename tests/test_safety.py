import pytest

from src.harness.safety import (
    SQLSafetyError,
    assert_safe_sql,
    validate_sql,
)


def test_select_is_allowed():
    result = validate_sql(
        "SELECT ArtistId, Name FROM Artist LIMIT 5"
    )

    assert result.is_safe is True
    assert result.normalized_sql is not None


def test_cte_select_is_allowed():
    sql = """
    WITH top_artists AS (
        SELECT ArtistId, Name
        FROM Artist
        LIMIT 5
    )
    SELECT *
    FROM top_artists
    """

    result = validate_sql(sql)

    assert result.is_safe is True


def test_union_is_allowed():
    sql = """
    SELECT Name
    FROM Artist

    UNION

    SELECT Name
    FROM Genre
    """

    result = validate_sql(sql)

    assert result.is_safe is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM Artist",
        "UPDATE Artist SET Name = 'HACKED'",
        "INSERT INTO Artist (Name) VALUES ('HACKED')",
        "DROP TABLE Artist",
        "CREATE TABLE hacked (id INTEGER)",
        "ALTER TABLE Artist ADD COLUMN hacked TEXT",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE ':memory:' AS hacked",
        "VACUUM",
    ],
)
def test_write_or_admin_sql_is_blocked(sql):
    result = validate_sql(sql)

    assert result.is_safe is False


def test_multiple_statements_are_blocked():
    sql = """
    SELECT * FROM Artist;
    DELETE FROM Artist;
    """

    result = validate_sql(sql)

    assert result.is_safe is False
    assert "one SQL statement" in result.reason


def test_invalid_sql_is_blocked():
    result = validate_sql(
        "SELEC * FORM Artist"
    )

    assert result.is_safe is False


def test_empty_sql_is_blocked():
    result = validate_sql("")

    assert result.is_safe is False


def test_dangerous_keyword_inside_string_is_allowed():
    sql = """
    SELECT 'DELETE FROM Artist' AS example_text
    """

    result = validate_sql(sql)

    assert result.is_safe is True


def test_assert_safe_sql_returns_normalized_sql():
    sql = "SELECT Name FROM Artist LIMIT 3"

    normalized = assert_safe_sql(sql)

    assert "SELECT" in normalized
    assert "Artist" in normalized


def test_assert_safe_sql_raises_for_delete():
    with pytest.raises(SQLSafetyError):
        assert_safe_sql(
            "DELETE FROM Artist"
        )