from src.agent.router import route_after_validation
from src.agent.state import create_initial_state


def test_success_routes_to_end():
    state = create_initial_state(
        "test"
    )

    state["validation_status"] = "success"

    assert (
        route_after_validation(state)
        == "report"
    )


def test_error_routes_to_retry():
    state = create_initial_state(
        "test"
    )

    state["validation_status"] = "error"
    state["retry_count"] = 0

    assert (
        route_after_validation(state)
        == "retry"
    )


def test_empty_routes_to_retry():
    state = create_initial_state(
        "test"
    )

    state["validation_status"] = "empty"
    state["retry_count"] = 1

    assert (
        route_after_validation(state)
        == "retry"
    )


def test_retry_limit_routes_to_failure():
    state = create_initial_state(
        "test",
        max_retries=3,
    )

    state["validation_status"] = "error"
    state["retry_count"] = 3

    assert (
        route_after_validation(state)
        == "fail"
    )


def test_zero_retries_fails_immediately():
    state = create_initial_state(
        "test",
        max_retries=0,
    )

    state["validation_status"] = "error"

    assert (
        route_after_validation(state)
        == "fail"
    )