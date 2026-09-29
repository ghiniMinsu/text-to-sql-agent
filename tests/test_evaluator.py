
from src.harness.evaluator import (
    Benchmark,
    EvalHarness,
    SafetyEvalCase,
    TextToSQLEvalCase,
)


class FakeGraph:
    def __init__(
        self,
        responses: dict[str, dict],
    ) -> None:
        self.responses = responses

    def invoke(
        self,
        input: dict,
    ) -> dict:
        question = input[
            "question"
        ]

        return self.responses[
            question
        ]


def test_evaluator_first_pass_success():
    question = "first pass"

    graph = FakeGraph(
        {
            question: {
                "validation_status": "success",
                "retry_count": 0,
                "generated_sql": (
                    "SELECT name FROM customers"
                ),
                "query_columns": (
                    "name",
                ),
                "query_rows": (
                    ("Bob",),
                ),
                "error_message": None,
            }
        }
    )

    harness = EvalHarness(
        graph
    )

    case = TextToSQLEvalCase(
        id="case-1",
        question=question,
        expected_rows=(
            ("Bob",),
        ),
    )

    result = (
        harness
        .evaluate_text_to_sql_case(
            case
        )
    )

    assert (
        result.validation_status
        == "success"
    )

    assert (
        result.first_pass_success
        is True
    )

    assert (
        result.retry_count
        == 0
    )

    assert (
        result.answer_correct
        is True
    )


def test_evaluator_detects_recovery():
    question = "recovered"

    graph = FakeGraph(
        {
            question: {
                "validation_status": "success",
                "retry_count": 1,
                "generated_sql": (
                    "SELECT name FROM customers"
                ),
                "query_columns": (
                    "name",
                ),
                "query_rows": (
                    ("Bob",),
                ),
                "error_message": None,
            }
        }
    )

    harness = EvalHarness(
        graph
    )

    case = TextToSQLEvalCase(
        id="case-2",
        question=question,
        expected_rows=(
            ("Bob",),
        ),
    )

    result = (
        harness
        .evaluate_text_to_sql_case(
            case
        )
    )

    assert (
        result.first_pass_success
        is False
    )

    assert (
        result.initial_failure
        is True
    )

    assert (
        result.recovered_by_self_correction
        is True
    )

    assert (
        result.retry_count
        == 1
    )


def test_evaluator_detects_final_failure():
    question = "failed"

    graph = FakeGraph(
        {
            question: {
                "validation_status": "failed",
                "retry_count": 3,
                "generated_sql": (
                    "SELECT bad_column "
                    "FROM customers"
                ),
                "query_columns": (),
                "query_rows": (),
                "error_message": (
                    "no such column: bad_column"
                ),
            }
        }
    )

    harness = EvalHarness(
        graph
    )

    case = TextToSQLEvalCase(
        id="case-3",
        question=question,
    )

    result = (
        harness
        .evaluate_text_to_sql_case(
            case
        )
    )

    assert (
        result.validation_status
        == "failed"
    )

    assert (
        result.retry_count
        == 3
    )

    assert (
        result.recovered_by_self_correction
        is False
    )


def test_safety_case_blocks_delete():
    graph = FakeGraph(
        {}
    )

    harness = EvalHarness(
        graph
    )

    case = SafetyEvalCase(
        id="delete",
        sql="DELETE FROM Artist",
        expected_blocked=True,
    )

    result = (
        harness
        .evaluate_safety_case(
            case
        )
    )

    assert (
        result.actually_blocked
        is True
    )

    assert (
        result.correct
        is True
    )


def test_safety_case_allows_select():
    graph = FakeGraph(
        {}
    )

    harness = EvalHarness(
        graph
    )

    case = SafetyEvalCase(
        id="select",
        sql=(
            "SELECT Name "
            "FROM Artist LIMIT 5"
        ),
        expected_blocked=False,
    )

    result = (
        harness
        .evaluate_safety_case(
            case
        )
    )

    assert (
        result.actually_blocked
        is False
    )

    assert (
        result.correct
        is True
    )


def test_evaluation_summary():
    graph = FakeGraph(
        {
            "first": {
                "validation_status": "success",
                "retry_count": 0,
                "generated_sql": "SELECT 1",
                "query_columns": (
                    "value",
                ),
                "query_rows": (
                    (1,),
                ),
                "error_message": None,
            },

            "recovered": {
                "validation_status": "success",
                "retry_count": 1,
                "generated_sql": "SELECT 2",
                "query_columns": (
                    "value",
                ),
                "query_rows": (
                    (2,),
                ),
                "error_message": None,
            },

            "failed": {
                "validation_status": "failed",
                "retry_count": 3,
                "generated_sql": (
                    "SELECT invalid"
                ),
                "query_columns": (),
                "query_rows": (),
                "error_message": (
                    "no such column"
                ),
            },
        }
    )

    benchmark = Benchmark(
        text_to_sql_cases=(
            TextToSQLEvalCase(
                id="first",
                question="first",
                expected_rows=(
                    (1,),
                ),
            ),

            TextToSQLEvalCase(
                id="recovered",
                question="recovered",
                expected_rows=(
                    (2,),
                ),
            ),

            TextToSQLEvalCase(
                id="failed",
                question="failed",
            ),
        ),

        safety_cases=(
            SafetyEvalCase(
                id="delete",
                sql="DELETE FROM Artist",
                expected_blocked=True,
            ),

            SafetyEvalCase(
                id="select",
                sql=(
                    "SELECT Name "
                    "FROM Artist"
                ),
                expected_blocked=False,
            ),
        ),
    )

    harness = EvalHarness(
        graph
    )

    report = harness.evaluate(
        benchmark
    )

    summary = report.summary

    assert (
        summary.total_text_to_sql_cases
        == 3
    )

    assert (
        summary.first_pass_success_count
        == 1
    )

    assert (
        summary.final_success_count
        == 2
    )

    assert (
        summary.initial_failure_count
        == 2
    )

    assert (
        summary.self_correction_recovery_count
        == 1
    )

    assert (
        summary.self_correction_recovery_rate
        == 0.5
    )

    assert (
        summary.answer_evaluated_count
        == 2
    )

    assert (
        summary.answer_accuracy
        == 1.0
    )

    assert (
        summary.safety_block_rate
        == 1.0
    )

    assert (
        summary.safety_policy_accuracy
        == 1.0
    )