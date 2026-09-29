import sqlite3
from typing import Protocol

from src.agent.state import AgentState
from src.harness.database import SQLiteReadOnlyExecutor
from src.harness.safety import (
    SQLSafetyError,
    assert_safe_sql,
)
from src.harness.schema import SQLiteSchemaInspector


class SQLGeneratorProtocol(Protocol):
    def generate_sql(
        self,
        question: str,
        schema_context: str,
        correction_feedback: str | None = None,
    ) -> str:
        ...

class BusinessReportGeneratorProtocol(Protocol):
    def generate_report(
        self,
        state: AgentState,
    ) -> dict:
        if self.report_generator is None:
            raise RuntimeError(
                "Business report generator is not configured."
            )

        if state.get(
            "validation_status"
        ) != "success":
            raise ValueError(
                "Business report can only be generated "
                "for a successful query."
            )

        report = (
            self.report_generator.generate_report(
                question=state["question"],
                generated_sql=state["generated_sql"],
                query_columns=state["query_columns"],
                query_rows=state["query_rows"],
                row_count=state["row_count"],
            )
        )

        return {
            "business_report": report,
        }

class TextToSQLNodes:
    def __init__(
        self,
        generator: SQLGeneratorProtocol,
        schema_inspector: SQLiteSchemaInspector,
        db_executor: SQLiteReadOnlyExecutor,
        report_generator: BusinessReportGeneratorProtocol | None = None,
    ) -> None:
        self.generator = generator
        self.schema_inspector = schema_inspector
        self.db_executor = db_executor
        self.report_generator = report_generator

    def prepare_schema(
        self,
        state: AgentState,
    ) -> dict:
        """
        Load database metadata and create the
        schema context used by the LLM.
        """

        schema = self.schema_inspector.inspect()

        return {
            "schema_context": schema.to_prompt(),
        }

    def generate_report(
        self,
        state: AgentState,
    ) -> dict:
        """
        Generate a user-facing business report
        from the actual executed query result.
        """

        if self.report_generator is None:
            raise RuntimeError(
                "Business report generator is not configured."
            )

        if state.get("validation_status") != "success":
            raise ValueError(
                "Business report can only be generated "
                "for a successful query."
            )

        report = self.report_generator.generate_report(
            question=state["question"],
            generated_sql=state["generated_sql"],
            query_columns=state["query_columns"],
            query_rows=state["query_rows"],
            row_count=state["row_count"],
        )

        return {
            "business_report": report,
        }
    
    def generate_sql(
        self,
        state: AgentState,
    ) -> dict:
        feedback = state.get(
            "error_message"
        )

        sql = self.generator.generate_sql(
            question=state["question"],
            schema_context=state["schema_context"],
            correction_feedback=feedback,
        )

        return {
            "generated_sql": sql,
            "query_columns": (),
            "query_rows": (),
            "row_count": 0,
            "business_report": "",
            "error_message": None,
            "validation_status": "pending",
        }

    def execute_sql(
        self,
        state: AgentState,
    ) -> dict:
        """
        Validate SQL through the Safety Harness
        and execute it using the read-only DB executor.
        """

        sql = state["generated_sql"]

        try:
            safe_sql = assert_safe_sql(sql)

            result = self.db_executor.execute(
                safe_sql
            )

            return {
                "generated_sql": safe_sql,
                "query_columns": result.columns,
                "query_rows": result.rows,
                "row_count": result.row_count,
                "error_message": None,
            }

        except SQLSafetyError as exc:
            return {
                "query_columns": (),
                "query_rows": (),
                "row_count": 0,
                "error_message": (
                    f"Safety validation failed: {exc}"
                ),
            }

        except sqlite3.Error as exc:
            return {
                "query_columns": (),
                "query_rows": (),
                "row_count": 0,
                "error_message": (
                    f"SQL execution failed: {exc}"
                ),
            }

    def validate_result(
        self,
        state: AgentState,
    ) -> dict:
        """
        Decide whether the SQL execution succeeded.

        SQL error:
            validation_status = error

        Empty result:
            validation_status = empty

        Valid rows:
            validation_status = success
        """

        error_message = state.get(
            "error_message"
        )

        if error_message:
            return {
                "validation_status": "error",
            }

        row_count = state.get(
            "row_count",
            0,
        )

        if row_count == 0:
            return {
                "validation_status": "empty",
                "error_message": (
                    "Query returned an empty result set. "
                    "Review table relationships, filters, "
                    "column names, and query conditions."
                ),
            }

        return {
            "validation_status": "success",
            "error_message": None,
        }

    def prepare_retry(
        self,
        state: AgentState,
    ) -> dict:
        """
        Increment retry counter before another
        LLM correction attempt.
        """

        retry_count = state.get(
            "retry_count",
            0,
        )

        return {
            "retry_count": retry_count + 1,
        }
    
    def finalize_failure(
        self,
        state: AgentState,
    ) -> dict:
        """
        Mark the workflow as failed after
        exhausting all self-correction attempts.
        """

        return {
            "validation_status": "failed",
        }