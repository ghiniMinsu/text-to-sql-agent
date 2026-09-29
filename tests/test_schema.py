import sqlite3

import pytest

from src.harness.schema import SQLiteSchemaInspector


@pytest.fixture
def schema_db(tmp_path):
    db_path = tmp_path / "schema_test.db"

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
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY (customer_id)
                REFERENCES customers(id)
        )
        """
    )

    connection.commit()
    connection.close()

    return db_path


def test_inspector_finds_tables(schema_db):
    inspector = SQLiteSchemaInspector(schema_db)

    schema = inspector.inspect()

    table_names = [
        table.name
        for table in schema.tables
    ]

    assert table_names == [
        "customers",
        "orders",
    ]


def test_inspector_finds_columns(schema_db):
    inspector = SQLiteSchemaInspector(schema_db)

    schema = inspector.inspect()

    customers = next(
        table
        for table in schema.tables
        if table.name == "customers"
    )

    column_names = [
        column.name
        for column in customers.columns
    ]

    assert column_names == [
        "id",
        "name",
    ]


def test_inspector_detects_primary_key(schema_db):
    inspector = SQLiteSchemaInspector(schema_db)

    schema = inspector.inspect()

    customers = next(
        table
        for table in schema.tables
        if table.name == "customers"
    )

    id_column = next(
        column
        for column in customers.columns
        if column.name == "id"
    )

    assert id_column.primary_key is True
    assert id_column.nullable is False


def test_inspector_detects_foreign_key(schema_db):
    inspector = SQLiteSchemaInspector(schema_db)

    schema = inspector.inspect()

    orders = next(
        table
        for table in schema.tables
        if table.name == "orders"
    )

    assert len(orders.foreign_keys) == 1

    foreign_key = orders.foreign_keys[0]

    assert foreign_key.column == "customer_id"
    assert foreign_key.referenced_table == "customers"
    assert foreign_key.referenced_column == "id"


def test_schema_can_be_converted_to_prompt(schema_db):
    inspector = SQLiteSchemaInspector(schema_db)

    schema = inspector.inspect()

    prompt = schema.to_prompt()

    assert "DATABASE SCHEMA" in prompt
    assert "Table: customers" in prompt
    assert "Table: orders" in prompt
    assert "customer_id -> customers.id" in prompt


def test_missing_database():
    with pytest.raises(FileNotFoundError):
        SQLiteSchemaInspector(
            "does-not-exist.db"
        )