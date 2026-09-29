from dataclasses import dataclass

from sqlglot import parse
from sqlglot.errors import ParseError
from sqlglot.expressions.ddl import DDL
from sqlglot.expressions.dml import DML
from sqlglot.expressions.query import Query


@dataclass(frozen=True)
class SafetyResult:
    is_safe: bool
    reason: str
    normalized_sql: str | None = None


class SQLSafetyError(ValueError):
    """Raised when SQL violates the read-only safety policy."""


def validate_sql(sql: str) -> SafetyResult:
    """
    Validate SQL before execution.

    Policy:
    - Empty SQL is rejected.
    - Only one SQL statement is allowed.
    - Only query expressions are allowed.
    - DML / DDL nodes are rejected.
    - SELECT ... INTO style constructs are rejected.
    """

    if not sql or not sql.strip():
        return SafetyResult(
            is_safe=False,
            reason="SQL is empty.",
        )

    try:
        statements = [
            statement
            for statement in parse(sql, read="sqlite")
            if statement is not None
        ]

    except ParseError as exc:
        return SafetyResult(
            is_safe=False,
            reason=f"SQL parse error: {exc}",
        )

    if len(statements) != 1:
        return SafetyResult(
            is_safe=False,
            reason="Exactly one SQL statement is allowed.",
        )

    statement = statements[0]

    # Allow-list:
    # SELECT / UNION / INTERSECT / EXCEPT / WITH ... SELECT 등
    if not isinstance(statement, Query):
        return SafetyResult(
            is_safe=False,
            reason=(
                "Only read-only query statements are allowed. "
                f"Received: {type(statement).__name__}"
            ),
        )

    # Defensive AST traversal.
    # Query 내부에 쓰기/DDL 표현이 숨어 있는 경우까지 차단한다.
    for node in statement.walk():
        if isinstance(node, DML):
            return SafetyResult(
                is_safe=False,
                reason=(
                    "DML statements are not allowed: "
                    f"{type(node).__name__}"
                ),
            )

        if isinstance(node, DDL):
            return SafetyResult(
                is_safe=False,
                reason=(
                    "DDL statements are not allowed: "
                    f"{type(node).__name__}"
                ),
            )

        # SELECT ... INTO 등
        if type(node).__name__ == "Into":
            return SafetyResult(
                is_safe=False,
                reason="SELECT INTO is not allowed.",
            )

    normalized_sql = statement.sql(
        dialect="sqlite",
        pretty=False,
    )

    return SafetyResult(
        is_safe=True,
        reason="SQL passed read-only safety validation.",
        normalized_sql=normalized_sql,
    )


def assert_safe_sql(sql: str) -> str:
    """
    Validate SQL and return normalized SQL.

    Raises:
        SQLSafetyError: if SQL is unsafe.
    """

    result = validate_sql(sql)

    if not result.is_safe:
        raise SQLSafetyError(result.reason)

    assert result.normalized_sql is not None

    return result.normalized_sql