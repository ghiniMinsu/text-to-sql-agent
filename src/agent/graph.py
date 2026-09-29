from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from src.agent.nodes import TextToSQLNodes
from src.agent.router import route_after_validation
from src.agent.state import AgentState


def build_text_to_sql_graph(
    nodes: TextToSQLNodes,
):
    """
    Build and compile the Text-to-SQL workflow.

    Flow:
        START
          -> prepare_schema
          -> generate_sql
          -> execute_sql
          -> validate_result

    On success:
        -> generate_report
        -> END

    On SQL error / empty result:
        -> prepare_retry
        -> generate_sql

    When retry limit is exhausted:
        -> finalize_failure
        -> END
    """

    builder = StateGraph(AgentState)

    # -------------------------
    # Nodes
    # -------------------------

    builder.add_node(
        "prepare_schema",
        nodes.prepare_schema,
    )

    builder.add_node(
        "generate_sql",
        nodes.generate_sql,
    )

    builder.add_node(
        "execute_sql",
        nodes.execute_sql,
    )

    builder.add_node(
        "validate_result",
        nodes.validate_result,
    )

    builder.add_node(
        "prepare_retry",
        nodes.prepare_retry,
    )

    builder.add_node(
        "generate_report",
        nodes.generate_report,
    )

    builder.add_node(
        "finalize_failure",
        nodes.finalize_failure,
    )

    # -------------------------
    # Main execution flow
    # -------------------------

    builder.add_edge(
        START,
        "prepare_schema",
    )

    builder.add_edge(
        "prepare_schema",
        "generate_sql",
    )

    builder.add_edge(
        "generate_sql",
        "execute_sql",
    )

    builder.add_edge(
        "execute_sql",
        "validate_result",
    )

    # -------------------------
    # Conditional routing
    # -------------------------

    builder.add_conditional_edges(
        "validate_result",
        route_after_validation,
        {
            "report": "generate_report",
            "retry": "prepare_retry",
            "fail": "finalize_failure",
        },
    )

    # -------------------------
    # Self-correction loop
    # -------------------------

    builder.add_edge(
        "prepare_retry",
        "generate_sql",
    )

    # -------------------------
    # Terminal paths
    # -------------------------

    builder.add_edge(
        "generate_report",
        END,
    )

    builder.add_edge(
        "finalize_failure",
        END,
    )

    return builder.compile()