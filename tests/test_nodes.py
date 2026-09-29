
import sqlite3

import pytest

from src.agent.nodes import TextToSQLNodes
from src.agent.state import create_initial_state
from src.harness.database import SQLiteReadOnlyExecutor
from src.harness.schema import SQLiteSchemaInspector


class FakeSQLGenerator:
    def __init__(
        self,
        sql: str,
    ) -> None:
        self.sql = sql
        self.last_feedback = None

    def generate_sql(
        self,
        question: str,
        schema_context: str,
        correction_feedback: str | None = None,
    ) -> str:
        self.last_feedback = correction_feedback

        return self.sql


@pytest.fixture
def sample_db(tmp_path):
    db_path = tmp_path / "agent_test.db"

    connection = sqlite3.connect(db_path)

    connection.execute(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
        """
    )

    connection.execute(
        """
        INSERT INTO customers (name)
        VALUES ('Alice')
        """
    )

    connection.execute(
        """
        INSERT INTO customers (name)
        VALUES ('Bob')
        """
    )

    connection.commit()
    connection.close()

    return db_path


def create_nodes(
    sample_db,
    sql: str,
):
    generator = FakeSQLGenerator(sql)

    inspector = SQLiteSchemaInspector(
        sample_db
    )

    executor = SQLiteReadOnlyExecutor(
        sample_db
    )

    nodes = TextToSQLNodes(
        generator=generator,
        schema_inspector=inspector,
        db_executor=executor,
    )

    return nodes, generator


def test_prepare_schema(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "고객을 보여줘"
    )

    update = nodes.prepare_schema(state)

    assert "Table: customers" in (
        update["schema_context"]
    )


def test_generate_sql(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "고객을 보여줘"
    )

    state.update(
        nodes.prepare_schema(state)
    )

    update = nodes.generate_sql(state)

    assert (
        update["generated_sql"]
        == "SELECT * FROM customers"
    )


def test_execute_sql_success(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT id, name FROM customers",
    )

    state = create_initial_state(
        "고객을 보여줘"
    )

    state["generated_sql"] = (
        "SELECT id, name FROM customers"
    )

    update = nodes.execute_sql(state)

    assert update["row_count"] == 2

    assert update["query_columns"] == (
        "id",
        "name",
    )


def test_dangerous_sql_is_blocked(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "DELETE FROM customers",
    )

    state = create_initial_state(
        "고객 삭제"
    )

    state["generated_sql"] = (
        "DELETE FROM customers"
    )

    update = nodes.execute_sql(state)

    assert update["row_count"] == 0

    assert (
        "Safety validation failed"
        in update["error_message"]
    )


def test_validation_success(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "고객"
    )

    state["row_count"] = 2
    state["error_message"] = None

    update = nodes.validate_result(state)

    assert (
        update["validation_status"]
        == "success"
    )


def test_empty_result_triggers_correction(
    sample_db,
):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "없는 고객"
    )

    state["row_count"] = 0
    state["error_message"] = None

    update = nodes.validate_result(state)

    assert (
        update["validation_status"]
        == "empty"
    )

    assert update["error_message"]


def test_sql_error_triggers_correction(
    sample_db,
):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT invalid_column FROM customers",
    )

    state = create_initial_state(
        "고객"
    )

    state["error_message"] = (
        "SQL execution failed: "
        "no such column: invalid_column"
    )

    update = nodes.validate_result(state)

    assert (
        update["validation_status"]
        == "error"
    )


def test_feedback_is_sent_to_generator(
    sample_db,
):
    nodes, generator = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "고객"
    )

    state["schema_context"] = (
        "Table: customers"
    )

    state["error_message"] = (
        "no such column: customer_name"
    )

    nodes.generate_sql(state)

    assert generator.last_feedback == (
        "no such column: customer_name"
    )


def test_prepare_retry(sample_db):
    nodes, _ = create_nodes(
        sample_db,
        "SELECT * FROM customers",
    )

    state = create_initial_state(
        "고객"
    )

    assert state["retry_count"] == 0

    update = nodes.prepare_retry(state)

    assert update["retry_count"] == 1