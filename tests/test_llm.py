import pytest

from src.agent.llm import extract_sql
from src.agent.prompts import (
    build_report_messages,
    build_sql_messages,
)


def test_extract_plain_sql():
    sql = extract_sql(
        "SELECT * FROM Artist;"
    )

    assert sql == "SELECT * FROM Artist;"


def test_extract_markdown_sql():
    content = """```sql
SELECT * FROM Artist;
```"""

    sql = extract_sql(content)

    assert sql == "SELECT * FROM Artist;"


def test_empty_llm_response_is_rejected():
    with pytest.raises(ValueError):
        extract_sql("   ")


def test_prompt_contains_question_and_schema():
    messages = build_sql_messages(
        question="아티스트 수를 알려줘",
        schema_context=(
            "Table: Artist\n"
            "- ArtistId INTEGER\n"
            "- Name TEXT"
        ),
    )

    assert len(messages) == 2

    system_role, system_message = messages[0]
    human_role, human_message = messages[1]

    assert system_role == "system"
    assert human_role == "human"

    assert "SQLite" in system_message
    assert "아티스트 수를 알려줘" in human_message
    assert "Table: Artist" in human_message


def test_prompt_contains_correction_feedback():
    messages = build_sql_messages(
        question="아티스트 수",
        schema_context="Table: Artist",
        correction_feedback="no such column: artist_name",
    )

    human_message = messages[1][1]

    assert "PREVIOUS ATTEMPT FEEDBACK" in human_message
    assert "no such column: artist_name" in human_message


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        build_sql_messages(
            question="",
            schema_context="Table: Artist",
        )

def test_report_prompt_contains_real_query_result():
    messages = build_report_messages(
        question="매출이 가장 높은 고객은?",
        generated_sql=(
            "SELECT name, total "
            "FROM customers"
        ),
        query_columns=(
            "name",
            "total",
        ),
        query_rows=(
            ("Alice", 100.0),
            ("Bob", 200.0),
        ),
        row_count=2,
    )

    assert len(messages) == 2

    human_message = messages[1][1]

    assert "Alice" in human_message
    assert "Bob" in human_message
    assert "200.0" in human_message
    assert "row_count" in human_message

def test_local_sql_generator_can_be_imported():
    from src.agent.llm import LocalSQLGenerator

    assert LocalSQLGenerator is not None