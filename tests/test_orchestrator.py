"""Unit tests for Workflow Orchestrator (State Machine Guards)."""

import pytest
from fastapi import HTTPException
from app.models.enums import ClaimStatus
from app.services.orchestrator import WorkflowOrchestrator


def test_valid_state_transitions():
    orch = WorkflowOrchestrator()

    # SUBMITTED -> VALIDATED
    orch.guard_transition(ClaimStatus.SUBMITTED.value, ClaimStatus.VALIDATED.value)

    # VALIDATED -> POLICY_CHECK
    orch.guard_transition(ClaimStatus.VALIDATED.value, ClaimStatus.POLICY_CHECK.value)

    # POLICY_CHECK -> FRAUD_CHECK
    orch.guard_transition(ClaimStatus.POLICY_CHECK.value, ClaimStatus.FRAUD_CHECK.value)

    # FRAUD_CHECK -> UNDER_REVIEW
    orch.guard_transition(ClaimStatus.FRAUD_CHECK.value, ClaimStatus.UNDER_REVIEW.value)

    # UNDER_REVIEW -> APPROVED
    orch.guard_transition(ClaimStatus.UNDER_REVIEW.value, ClaimStatus.APPROVED.value)

    # APPROVED -> SETTLED
    orch.guard_transition(ClaimStatus.APPROVED.value, ClaimStatus.SETTLED.value)


def test_illegal_transition_rejection():
    orch = WorkflowOrchestrator()

    # Direct SUBMITTED -> SETTLED should fail with 400
    with pytest.raises(HTTPException) as exc_info:
        orch.guard_transition(ClaimStatus.SUBMITTED.value, ClaimStatus.SETTLED.value)

    assert exc_info.value.status_code == 400
    assert "Invalid state transition" in exc_info.value.detail


def test_terminal_state_rejection():
    orch = WorkflowOrchestrator()

    # SETTLED is terminal
    with pytest.raises(HTTPException) as exc_info:
        orch.guard_transition(ClaimStatus.SETTLED.value, ClaimStatus.UNDER_REVIEW.value)

    assert exc_info.value.status_code == 400
