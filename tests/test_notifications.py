"""Unit tests for Notification Service & WhatsApp Template Generator."""

from app.services.notification_service import dispatch_claim_notification, format_whatsapp_message


def test_submitted_notification_template():
    msg = format_whatsapp_message(
        claim_number="CLM-1001",
        patient_name="Rahul Sharma",
        status="SUBMITTED",
    )
    assert "Rahul Sharma" in msg
    assert "CLM-1001" in msg
    assert "submitted to the insurer" in msg


def test_approved_with_copay_notification_template():
    msg = format_whatsapp_message(
        claim_number="CLM-1002",
        patient_name="Priya Patel",
        status="APPROVED",
        approved_amount_paise=9000000,  # ₹90,000 approved
        billed_paise=10000000,  # ₹1,00,000 billed (₹10,000 copay)
    )
    assert "Priya Patel" in msg
    assert "APPROVED for ₹90,000" in msg
    assert "Out-of-pocket co-pay required: ₹10,000" in msg


def test_settled_notification_template():
    msg = format_whatsapp_message(
        claim_number="CLM-1003",
        patient_name="Amit Kumar",
        status="SETTLED",
        approved_amount_paise=5000000,
    )
    assert "payout of ₹50,000 has been settled directly" in msg


def test_dispatch_notification_payload():
    payload = dispatch_claim_notification(
        claim_number="CLM-1004",
        patient_name="Sunita Rao",
        status="APPROVED",
        phone="+919876543210",
        approved_amount_paise=6000000,
    )
    assert payload.phone == "+919876543210"
    assert payload.claim_number == "CLM-1004"
    assert payload.status == "APPROVED"
    assert "Sunita Rao" in payload.message
