import pytest

from services.ride_service.state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    RideStatus,
    can_transition,
    validate_transition,
)

S = RideStatus


@pytest.mark.parametrize(
    "current,target",
    [
        (S.DRIVER_ASSIGNED, S.ACCEPTED),
        (S.DRIVER_ASSIGNED, S.CANCELLED),
        (S.ACCEPTED, S.IN_PROGRESS),
        (S.ACCEPTED, S.CANCELLED),
        (S.IN_PROGRESS, S.COMPLETED),
    ],
)
def test_valid_transitions(current, target):
    assert can_transition(current, target)
    validate_transition(current, target)  # does not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (S.DRIVER_ASSIGNED, S.IN_PROGRESS),  # can't skip accept
        (S.DRIVER_ASSIGNED, S.COMPLETED),
        (S.ACCEPTED, S.COMPLETED),  # can't skip start
        (S.IN_PROGRESS, S.CANCELLED),  # can't cancel mid-trip
        (S.COMPLETED, S.CANCELLED),
        (S.CANCELLED, S.ACCEPTED),
        (S.ACCEPTED, S.ACCEPTED),  # no self-loops
    ],
)
def test_invalid_transitions(current, target):
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError):
        validate_transition(current, target)


def test_every_status_has_a_rule():
    assert set(ALLOWED_TRANSITIONS) == set(RideStatus)


@pytest.mark.parametrize("final", [S.COMPLETED, S.CANCELLED])
def test_final_states_have_no_exits(final):
    assert ALLOWED_TRANSITIONS[final] == frozenset()


def test_error_message_lists_allowed_moves():
    with pytest.raises(InvalidTransitionError) as info:
        validate_transition(S.ACCEPTED, S.COMPLETED)
    assert "cancelled" in str(info.value) and "in_progress" in str(info.value)
