import json
from pathlib import Path

from src.agent.graph import (
    build_text_to_sql_graph,
)
from src.agent.llm import (
    LocalBusinessReportGenerator,
    LocalSQLGenerator,
)
from src.agent.nodes import (
    TextToSQLNodes,
)
from src.harness.database import (
    SQLiteReadOnlyExecutor,
)
from src.harness.evaluator import (
    EvalHarness,
    load_benchmark,
)
from src.harness.schema import (
    SQLiteSchemaInspector,
)

PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent


DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "chinook.db"
)

BENCHMARK_PATH = (
    PROJECT_ROOT
    / "evals"
    / "benchmark.json"
)

RESULT_PATH = (
    PROJECT_ROOT
    / "evals"
    / "latest_results.json"
)


def build_agent_graph():
    generator = (
        LocalSQLGenerator()
    )

    report_generator = (
        LocalBusinessReportGenerator()
    )

    schema_inspector = (
        SQLiteSchemaInspector(
            DB_PATH
        )
    )

    db_executor = (
        SQLiteReadOnlyExecutor(
            DB_PATH
        )
    )

    nodes = TextToSQLNodes(
        generator=generator,
        report_generator=(
            report_generator
        ),
        schema_inspector=(
            schema_inspector
        ),
        db_executor=(
            db_executor
        ),
    )

    return build_text_to_sql_graph(
        nodes
    )


def main() -> None:
    benchmark = load_benchmark(
        BENCHMARK_PATH
    )

    graph = build_agent_graph()

    harness = EvalHarness(
        graph
    )

    report = harness.evaluate(
        benchmark
    )

    payload = report.to_dict()

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )

    RESULT_PATH.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "Evaluation result saved to:"
    )

    print(
        RESULT_PATH
    )


if __name__ == "__main__":
    main()