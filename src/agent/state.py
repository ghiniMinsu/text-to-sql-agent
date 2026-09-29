from typing import Any, Literal, TypedDict

ValidationStatus = Literal[
    "pending",
    "success",
    "error",
    "empty",
    "failed",
]


class AgentState(TypedDict, total=False):
    # User input
    question: str

    # Database metadata
    schema_context: str

    # LLM-generated SQL
    generated_sql: str

    # Query result
    query_columns: tuple[str, ...]
    query_rows: tuple[tuple[Any, ...], ...]
    row_count: int

    # Business report
    business_report: str

    # Validation / correction
    error_message: str | None
    validation_status: ValidationStatus

    # Loop control
    retry_count: int
    max_retries: int


def create_initial_state(
    question: str,
    max_retries: int = 3,
) -> AgentState:
    if not question.strip():
        raise ValueError(
            "Question must not be empty."
        )

    if max_retries < 0:
        raise ValueError(
            "max_retries must be >= 0."
        )

    return AgentState(
        question=question.strip(),
        schema_context="",
        generated_sql="",
        query_columns=(),
        query_rows=(),
        row_count=0,
        business_report="",
        error_message=None,
        validation_status="pending",
        retry_count=0,
        max_retries=max_retries,
    )