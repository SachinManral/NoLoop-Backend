"""Unit tests for Event Bus & Webhook Dispatcher."""

import pytest
from app.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_event_bus_register_and_publish():
    bus = EventBus()
    bus.register_webhook(
        tenant_id="tnt_apollo",
        topic="CLAIM_APPROVED",
        callback_url="http://localhost:9999/webhook",
    )
    assert len(bus._subscriptions) == 1

    evt = await bus.publish_event(
        topic="CLAIM_APPROVED",
        tenant_id="tnt_apollo",
        payload={"claimNumber": "CLM-9901", "approvedAmountPaise": 5000000},
    )
    assert evt.topic == "CLAIM_APPROVED"
    assert evt.tenant_id == "tnt_apollo"
    assert evt.payload["claimNumber"] == "CLM-9901"
