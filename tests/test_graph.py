import sqlite3

import pytest

from src.agent.graph import build_text_to_sql_graph
from src.agent.nodes import TextToSQLNodes
from src.agent.state import create_initial_state
from src.harness.database import SQLiteReadOnlyExecutor
from src.harness.schema import SQLiteSchemaInspector


class SequenceSQLGenerator:
    """
    Fake LLM that returns SQL statements
    in sequence.
    """

    def __init__(
        self,
        sql_sequence: list[str],
    ) -> None:
        self.sql_sequence = sql_sequence
        self.call_count = 0
        self.feedback_history: list[str | None] = []

    def generate_sql(
        self,
        question: str,
        schema_context: str,
        correction_feedback: str | None = None,
    ) -> str:
        self.feedback_history.append(
            correction_feedback
        )

        index = min(
            self.call_count,
            len(self.sql_sequence) - 1,
        )

        sql = self.sql_sequence[index]

        self.call_count += 1

        return sql


class FakeBusinessReportGenerator:
    """
    Fake report generator used so tests
    do not depend on Ollama.
    """

    def __init__(self) -> None:
        self.call_count = 0

    def generate_report(
        self,
        question: str,
        generated_sql: str,
        query_columns: tuple[str, ...],
        query_rows: tuple[tuple[object, ...], ...],
        row_count: int,
    ) -> str:
        self.call_count += 1

        return (
            f"분석 완료: 총 {row_count}개의 "
            f"결과를 확인했습니다."
        )


@pytest.fixture
def graph_db(tmp_path):
    db_path = tmp_path / "graph_test.db"

    connection = sqlite3.connect(
        db_path
    )

    connection.execute(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            total_spent REAL NOT NULL
        )
        """
    )

    connection.executemany(
        """
        INSERT INTO customers (
            name,
            total_spent
        )
        VALUES (?, ?)
        """,
        [
            ("Alice", 100.0),
            ("Bob", 200.0),
            ("Charlie", 150.0),
        ],
    )

    connection.commit()
    connection.close()

    return db_path


def build_test_graph(
    db_path,
    generator,
):
    inspector = SQLiteSchemaInspector(
        db_path
    )

    executor = SQLiteReadOnlyExecutor(
        db_path
    )

    report_generator = (
        FakeBusinessReportGenerator()
    )

    nodes = TextToSQLNodes(
        generator=generator,
        schema_inspector=inspector,
        db_executor=executor,
        report_generator=report_generator,
    )

    graph = build_text_to_sql_graph(
        nodes
    )

    return graph, report_generator


def test_graph_succeeds_first_try(
    graph_db,
):
    generator = SequenceSQLGenerator(
        [
            """
            SELECT name, total_spent
            FROM customers
            ORDER BY total_spent DESC
            LIMIT 1
            """
        ]
    )

    graph, report_generator = (
        build_test_graph(
            graph_db,
            generator,
        )
    )

    initial_state = create_initial_state(
        "가장 많이 구매한 고객"
    )

    result = graph.invoke(
        initial_state
    )

    assert (
        result["validation_status"]
        == "success"
    )

    assert result["retry_count"] == 0
    assert generator.call_count == 1

    assert (
        result["query_rows"][0][0]
        == "Bob"
    )

    assert result["business_report"]

    assert "분석 완료" in (
        result["business_report"]
    )

    assert report_generator.call_count == 1


def test_graph_self_corrects_sql_error(
    graph_db,
):
    generator = SequenceSQLGenerator(
        [
            # First attempt: invalid column
            """
            SELECT customer_name
            FROM customers
            """,

            # Second attempt: corrected SQL
            """
            SELECT name, total_spent
            FROM customers
            ORDER BY total_spent DESC
            LIMIT 1
            """,
        ]
    )

    graph, report_generator = (
        build_test_graph(
            graph_db,
            generator,
        )
    )

    initial_state = create_initial_state(
        "가장 많이 구매한 고객"
    )

    result = graph.invoke(
        initial_state
    )

    assert (
        result["validation_status"]
        == "success"
    )

    assert result["retry_count"] == 1
    assert generator.call_count == 2

    assert (
        result["query_rows"][0][0]
        == "Bob"
    )

    assert result["business_report"]

    assert report_generator.call_count == 1

    # Initial generation receives no feedback.
    assert (
        generator.feedback_history[0]
        is None
    )

    # Retry receives SQLite execution feedback.
    assert (
        "no such column"
        in generator.feedback_history[1]
    )


def test_graph_self_corrects_empty_result(
    graph_db,
):
    generator = SequenceSQLGenerator(
        [
            # First attempt returns no rows.
            """
            SELECT name
            FROM customers
            WHERE name = 'Nobody'
            """,

            # Second attempt corrects the query.
            """
            SELECT name
            FROM customers
            ORDER BY total_spent DESC
            LIMIT 1
            """,
        ]
    )

    graph, report_generator = (
        build_test_graph(
            graph_db,
            generator,
        )
    )

    result = graph.invoke(
        create_initial_state(
            "가장 많이 구매한 고객"
        )
    )

    assert (
        result["validation_status"]
        == "success"
    )

    assert result["retry_count"] == 1
    assert generator.call_count == 2

    assert (
        result["query_rows"][0][0]
        == "Bob"
    )

    assert (
        "empty result set"
        in generator.feedback_history[1]
    )

    assert result["business_report"]

    assert report_generator.call_count == 1


def test_graph_stops_after_max_retries(
    graph_db,
):
    generator = SequenceSQLGenerator(
        [
            """
            SELECT nonexistent_column
            FROM customers
            """
        ]
    )

    graph, report_generator = (
        build_test_graph(
            graph_db,
            generator,
        )
    )

    result = graph.invoke(
        create_initial_state(
            "고객 분석",
            max_retries=3,
        )
    )

    assert (
        result["validation_status"]
        == "failed"
    )

    assert result["retry_count"] == 3

    # Initial attempt + 3 correction attempts
    assert generator.call_count == 4

    assert (
        result["error_message"]
        is not None
    )

    assert (
        "no such column"
        in result["error_message"]
    )

    # Failed workflow must not generate
    # a business report.
    assert result["business_report"] == ""

    assert report_generator.call_count == 0