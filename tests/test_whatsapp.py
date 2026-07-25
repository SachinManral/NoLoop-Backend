"""Unit tests for WhatsApp Business Webhook & Message Sender endpoints."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_whatsapp_webhook_handshake_success():
    res = client.get(
        "/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=noloop_whatsapp_verify_token_2026&hub.challenge=CHALLENGE_123"
    )
    assert res.status_code == 200
    assert res.text == "CHALLENGE_123"


def test_whatsapp_webhook_handshake_failure():
    res = client.get(
        "/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=INVALID_TOKEN&hub.challenge=CHALLENGE_123"
    )
    assert res.status_code == 403


def test_whatsapp_send_template_message():
    res = client.post(
        "/whatsapp/send",
        json={
            "phone": "+919876543210",
            "message": "Test notification message",
            "claimNumber": "CLM-9001",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SENT"
    assert data["recipient"] == "+919876543210"
    assert "CLM-9001" in data["message"]
