"""Notification & Patient Communication Service for NoLoop Platform.

Sprint 2: Listens to claim lifecycle events and dispatches WhatsApp notification
payloads and webhook callbacks to patient, hospital, and insurer subscribers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("notification_service")


@dataclass
class WhatsAppPayload:
    phone: str
    message: str
    claim_number: str
    status: str


def format_whatsapp_message(
    claim_number: str,
    patient_name: str,
    status: str,
    approved_amount_paise: int | None = None,
    billed_paise: int | None = None,
) -> str:
    """Format a patient-friendly WhatsApp update message."""
    formatted_status = status.replace("_", " ").title()

    if status == "SUBMITTED":
        return (
            f"Hello {patient_name}, your cashless claim {claim_number} has been successfully "
            f"submitted to the insurer. We are processing it with AI adjudication."
        )

    if status == "UNDER_REVIEW":
        return (
            f"Update on claim {claim_number}: Your claim is under review by the insurance "
            f"medical adjudicator. No action is required from you at this moment."
        )

    if status == "APPROVED":
        approved_inr = f"₹{approved_amount_paise / 100:,.0f}" if approved_amount_paise else "as requested"
        copay_info = ""
        if billed_paise and approved_amount_paise and billed_paise > approved_amount_paise:
            copay_inr = f"₹{(billed_paise - approved_amount_paise) / 100:,.0f}"
            copay_info = f" Out-of-pocket co-pay required: {copay_inr}."
        return (
            f"Great news {patient_name}! Claim {claim_number} is APPROVED for {approved_inr}."
            f"{copay_info} You are ready for cashless discharge."
        )

    if status == "QUERIED":
        return (
            f"Notice for claim {claim_number}: The insurer has requested additional document "
            f"clarification. Your hospital billing desk is handling the response."
        )

    if status == "SETTLED":
        return (
            f"Claim {claim_number} payout of ₹{approved_amount_paise / 100:,.0f} has been "
            f"settled directly to the hospital via UPI rails. Claim complete!"
        )

    return f"Claim update {claim_number}: Status changed to {formatted_status}."


def dispatch_claim_notification(
    claim_number: str,
    patient_name: str,
    status: str,
    phone: str | None = None,
    approved_amount_paise: int | None = None,
    billed_paise: int | None = None,
) -> WhatsAppPayload:
    """Dispatch WhatsApp message payload for a claim status transition."""
    target_phone = phone or "+919876543210"
    msg = format_whatsapp_message(
        claim_number=claim_number,
        patient_name=patient_name,
        status=status,
        approved_amount_paise=approved_amount_paise,
        billed_paise=billed_paise,
    )

    payload = WhatsAppPayload(
        phone=target_phone,
        message=msg,
        claim_number=claim_number,
        status=status,
    )

    log.info(
        "Dispatched WhatsApp notification to %s for claim %s [Status: %s]",
        target_phone,
        claim_number,
        status,
    )
    return payload
