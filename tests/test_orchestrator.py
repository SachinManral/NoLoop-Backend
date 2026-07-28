"""Unit tests for Workflow Orchestrator (State Machine Guards)."""

import pytest
from starlette.exceptions import HTTPException
from app.models.enums import ClaimStatus
from app.services.orchestrator import guard_transition


def test_valid_state_transitions():
    # SUBMITTED -> VALIDATED
    guard_transition(ClaimStatus.SUBMITTED, ClaimStatus.VALIDATED)

    # VALIDATED -> POLICY_CHECK
    guard_transition(ClaimStatus.VALIDATED, ClaimStatus.POLICY_CHECK)

    # POLICY_CHECK -> FRAUD_CHECK
    guard_transition(ClaimStatus.POLICY_CHECK, ClaimStatus.FRAUD_CHECK)

    # FRAUD_CHECK -> UNDER_REVIEW
    guard_transition(ClaimStatus.FRAUD_CHECK, ClaimStatus.UNDER_REVIEW)

    # UNDER_REVIEW -> APPROVED
    guard_transition(ClaimStatus.UNDER_REVIEW, ClaimStatus.APPROVED)

    # APPROVED -> SETTLED
    guard_transition(ClaimStatus.APPROVED, ClaimStatus.SETTLED)


def test_illegal_transition_rejection():
    # Direct SUBMITTED -> SETTLED should fail with 400
    with pytest.raises(HTTPException) as exc_info:
        guard_transition(ClaimStatus.SUBMITTED, ClaimStatus.SETTLED)

    assert exc_info.value.status_code == 400
    assert "Invalid state transition" in exc_info.value.detail


def test_terminal_state_rejection():
    # SETTLED is terminal
    with pytest.raises(HTTPException) as exc_info:
        guard_transition(ClaimStatus.SETTLED, ClaimStatus.UNDER_REVIEW)

    assert exc_info.value.status_code == 400


