from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from src.agent.state import create_initial_state
from src.harness.safety import validate_sql


class GraphProtocol(Protocol):
    def invoke(
        self,
        input: dict[str, Any],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class TextToSQLEvalCase:
    id: str
    question: str
    expected_columns: tuple[str, ...] | None = None
    expected_rows: tuple[tuple[Any, ...], ...] | None = None
    max_retries: int = 3


@dataclass(frozen=True)
class SafetyEvalCase:
    id: str
    sql: str
    expected_blocked: bool = True


@dataclass(frozen=True)
class Benchmark:
    text_to_sql_cases: tuple[
        TextToSQLEvalCase,
        ...
    ]

    safety_cases: tuple[
        SafetyEvalCase,
        ...
    ]


@dataclass(frozen=True)
class TextToSQLEvalResult:
    id: str
    question: str

    validation_status: str

    retry_count: int

    first_pass_success: bool

    initial_failure: bool

    recovered_by_self_correction: bool

    answer_correct: bool | None

    elapsed_seconds: float

    generated_sql: str

    error_message: str | None


@dataclass(frozen=True)
class SafetyEvalResult:
    id: str

    sql: str

    expected_blocked: bool

    actually_blocked: bool

    correct: bool

    reason: str


@dataclass(frozen=True)
class EvalSummary:
    total_text_to_sql_cases: int

    first_pass_success_count: int
    first_pass_success_rate: float

    final_success_count: int
    final_success_rate: float

    answer_evaluated_count: int
    answer_correct_count: int
    answer_accuracy: float | None

    initial_failure_count: int
    self_correction_recovery_count: int
    self_correction_recovery_rate: float | None

    average_retry_count: float

    average_latency_seconds: float

    total_safety_cases: int
    unsafe_safety_cases: int
    unsafe_blocked_count: int

    safety_block_rate: float | None
    safety_policy_accuracy: float | None


@dataclass(frozen=True)
class EvalReport:
    text_to_sql_results: tuple[
        TextToSQLEvalResult,
        ...
    ]

    safety_results: tuple[
        SafetyEvalResult,
        ...
    ]

    summary: EvalSummary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_tuple_rows(
    value: list[list[Any]] | None,
) -> tuple[tuple[Any, ...], ...] | None:
    if value is None:
        return None

    return tuple(
        tuple(row)
        for row in value
    )


def load_benchmark(
    path: str | Path,
) -> Benchmark:
    benchmark_path = Path(path)

    with benchmark_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    text_to_sql_cases = []

    for item in payload.get(
        "text_to_sql_cases",
        [],
    ):
        expected_columns = item.get(
            "expected_columns"
        )

        text_to_sql_cases.append(
            TextToSQLEvalCase(
                id=item["id"],
                question=item["question"],
                expected_columns=(
                    tuple(expected_columns)
                    if expected_columns
                    is not None
                    else None
                ),
                expected_rows=_to_tuple_rows(
                    item.get(
                        "expected_rows"
                    )
                ),
                max_retries=item.get(
                    "max_retries",
                    3,
                ),
            )
        )

    safety_cases = []

    for item in payload.get(
        "safety_cases",
        [],
    ):
        safety_cases.append(
            SafetyEvalCase(
                id=item["id"],
                sql=item["sql"],
                expected_blocked=item.get(
                    "expected_blocked",
                    True,
                ),
            )
        )

    return Benchmark(
        text_to_sql_cases=tuple(
            text_to_sql_cases
        ),
        safety_cases=tuple(
            safety_cases
        ),
    )


class EvalHarness:
    def __init__(
        self,
        graph: GraphProtocol,
    ) -> None:
        self.graph = graph

    def _evaluate_answer(
        self,
        case: TextToSQLEvalCase,
        result: dict[str, Any],
    ) -> bool | None:
        """
        Compare actual result against optional
        benchmark gold data.

        If no expected result exists,
        answer correctness is not evaluated.
        """

        if (
            case.expected_rows is None
            and case.expected_columns is None
        ):
            return None

        if (
            result.get(
                "validation_status"
            )
            != "success"
        ):
            return False

        if case.expected_columns is not None:
            actual_columns = tuple(
                result.get(
                    "query_columns",
                    (),
                )
            )

            if (
                actual_columns
                != case.expected_columns
            ):
                return False

        if case.expected_rows is not None:
            actual_rows = tuple(
                tuple(row)
                for row in result.get(
                    "query_rows",
                    (),
                )
            )

            if (
                actual_rows
                != case.expected_rows
            ):
                return False

        return True

    def evaluate_text_to_sql_case(
        self,
        case: TextToSQLEvalCase,
    ) -> TextToSQLEvalResult:
        initial_state = (
            create_initial_state(
                question=case.question,
                max_retries=case.max_retries,
            )
        )

        start = perf_counter()

        try:
            result = self.graph.invoke(
                initial_state
            )

            elapsed = (
                perf_counter()
                - start
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (
                perf_counter()
                - start
            )

            return TextToSQLEvalResult(
                id=case.id,
                question=case.question,
                validation_status=(
                    "exception"
                ),
                retry_count=0,
                first_pass_success=False,
                initial_failure=False,
                recovered_by_self_correction=False,
                answer_correct=False,
                elapsed_seconds=elapsed,
                generated_sql="",
                error_message=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

        status = result.get(
            "validation_status",
            "unknown",
        )

        retry_count = result.get(
            "retry_count",
            0,
        )

        final_success = (
            status == "success"
        )

        first_pass_success = (
            final_success
            and retry_count == 0
        )

        initial_failure = (
            retry_count > 0
            or status == "failed"
        )

        recovered = (
            initial_failure
            and final_success
        )

        answer_correct = (
            self._evaluate_answer(
                case,
                result,
            )
        )

        return TextToSQLEvalResult(
            id=case.id,
            question=case.question,
            validation_status=status,
            retry_count=retry_count,
            first_pass_success=(
                first_pass_success
            ),
            initial_failure=(
                initial_failure
            ),
            recovered_by_self_correction=(
                recovered
            ),
            answer_correct=(
                answer_correct
            ),
            elapsed_seconds=elapsed,
            generated_sql=result.get(
                "generated_sql",
                "",
            ),
            error_message=result.get(
                "error_message"
            ),
        )

    @staticmethod
    def evaluate_safety_case(
        case: SafetyEvalCase,
    ) -> SafetyEvalResult:
        result = validate_sql(
            case.sql
        )

        actually_blocked = (
            not result.is_safe
        )

        correct = (
            actually_blocked
            == case.expected_blocked
        )

        return SafetyEvalResult(
            id=case.id,
            sql=case.sql,
            expected_blocked=(
                case.expected_blocked
            ),
            actually_blocked=(
                actually_blocked
            ),
            correct=correct,
            reason=result.reason,
        )

    def evaluate(
        self,
        benchmark: Benchmark,
    ) -> EvalReport:
        text_results = tuple(
            self.evaluate_text_to_sql_case(
                case
            )
            for case
            in benchmark.text_to_sql_cases
        )

        safety_results = tuple(
            self.evaluate_safety_case(
                case
            )
            for case
            in benchmark.safety_cases
        )

        summary = self._build_summary(
            text_results=text_results,
            safety_results=safety_results,
        )

        return EvalReport(
            text_to_sql_results=text_results,
            safety_results=safety_results,
            summary=summary,
        )

    @staticmethod
    def _build_summary(
        text_results: tuple[
            TextToSQLEvalResult,
            ...
        ],
        safety_results: tuple[
            SafetyEvalResult,
            ...
        ],
    ) -> EvalSummary:
        total = len(
            text_results
        )

        first_pass_success_count = sum(
            result.first_pass_success
            for result
            in text_results
        )

        final_success_count = sum(
            result.validation_status
            == "success"
            for result
            in text_results
        )

        answer_results = [
            result
            for result
            in text_results
            if result.answer_correct
            is not None
        ]

        answer_correct_count = sum(
            result.answer_correct is True
            for result
            in answer_results
        )

        initial_failure_results = [
            result
            for result
            in text_results
            if result.initial_failure
        ]

        recovered_count = sum(
            result.recovered_by_self_correction
            for result
            in initial_failure_results
        )

        average_retry_count = (
            sum(
                result.retry_count
                for result
                in text_results
            )
            / total
            if total
            else 0.0
        )

        average_latency_seconds = (
            sum(
                result.elapsed_seconds
                for result
                in text_results
            )
            / total
            if total
            else 0.0
        )

        unsafe_cases = [
            result
            for result
            in safety_results
            if result.expected_blocked
        ]

        unsafe_blocked_count = sum(
            result.actually_blocked
            for result
            in unsafe_cases
        )

        safety_correct_count = sum(
            result.correct
            for result
            in safety_results
        )

        return EvalSummary(
            total_text_to_sql_cases=total,

            first_pass_success_count=(
                first_pass_success_count
            ),
            first_pass_success_rate=(
                first_pass_success_count
                / total
                if total
                else 0.0
            ),

            final_success_count=(
                final_success_count
            ),
            final_success_rate=(
                final_success_count
                / total
                if total
                else 0.0
            ),

            answer_evaluated_count=len(
                answer_results
            ),
            answer_correct_count=(
                answer_correct_count
            ),
            answer_accuracy=(
                answer_correct_count
                / len(answer_results)
                if answer_results
                else None
            ),

            initial_failure_count=len(
                initial_failure_results
            ),
            self_correction_recovery_count=(
                recovered_count
            ),
            self_correction_recovery_rate=(
                recovered_count
                / len(
                    initial_failure_results
                )
                if initial_failure_results
                else None
            ),

            average_retry_count=(
                average_retry_count
            ),

            average_latency_seconds=(
                average_latency_seconds
            ),

            total_safety_cases=len(
                safety_results
            ),

            unsafe_safety_cases=len(
                unsafe_cases
            ),

            unsafe_blocked_count=(
                unsafe_blocked_count
            ),

            safety_block_rate=(
                unsafe_blocked_count
                / len(unsafe_cases)
                if unsafe_cases
                else None
            ),

            safety_policy_accuracy=(
                safety_correct_count
                / len(safety_results)
                if safety_results
                else None
            ),
        )