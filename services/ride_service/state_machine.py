"""
The ride lifecycle as a finite state machine. Pure Python, no dependencies.

    driver_assigned --accept--> accepted --start--> in_progress --complete--> completed
          |                         |
          +--------cancel-----------+-------------> cancelled

Keeping every legal move in one table means:
  * the rules are easy to read and explain,
  * every endpoint checks transitions the same way,
  * adding a new status is a one-line change here.
"""

from enum import StrEnum


class RideStatus(StrEnum):
    DRIVER_ASSIGNED = "driver_assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[RideStatus, frozenset[RideStatus]] = {
    RideStatus.DRIVER_ASSIGNED: frozenset({RideStatus.ACCEPTED, RideStatus.CANCELLED}),
    RideStatus.ACCEPTED: frozenset({RideStatus.IN_PROGRESS, RideStatus.CANCELLED}),
    RideStatus.IN_PROGRESS: frozenset({RideStatus.COMPLETED}),
    RideStatus.COMPLETED: frozenset(),
    RideStatus.CANCELLED: frozenset(),
}

ACTIVE_STATUSES: frozenset[RideStatus] = frozenset(
    {RideStatus.DRIVER_ASSIGNED, RideStatus.ACCEPTED, RideStatus.IN_PROGRESS}
)


class InvalidTransitionError(Exception):
    def __init__(self, current: RideStatus, target: RideStatus):
        self.current = current
        self.target = target
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[current]) or ["none - final state"]
        super().__init__(
            f"Cannot move a ride from '{current.value}' to '{target.value}'. "
            f"Allowed next statuses: {', '.join(allowed)}."
        )


def can_transition(current: RideStatus, target: RideStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def validate_transition(current: RideStatus, target: RideStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
