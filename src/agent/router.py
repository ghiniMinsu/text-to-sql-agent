from typing import Literal

from src.agent.state import AgentState

RouteDecision = Literal[
    "report",
    "retry",
    "fail",
]


def route_after_validation(
    state: AgentState,
) -> RouteDecision:
    """
    Decide what to do after query validation.

    success
        -> END

    error / empty + retries remaining
        -> retry

    error / empty + retries exhausted
        -> graceful failure
    """

    status = state.get(
        "validation_status",
        "pending",
    )

    if status == "success":
        return "report"

    if status not in {"error", "empty"}:
        raise ValueError(
            f"Unexpected validation status: {status}"
        )

    retry_count = state.get(
        "retry_count",
        0,
    )

    max_retries = state.get(
        "max_retries",
        3,
    )

    if retry_count < max_retries:
        return "retry"

    return "fail"