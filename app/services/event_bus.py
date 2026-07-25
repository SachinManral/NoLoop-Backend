"""Async Event Bus & Webhook Dispatcher for NoLoop Platform.

Sprint 4: Decoupled event bus fanning out claim lifecycle events (CLAIM_SUBMITTED,
CLAIM_APPROVED, CLAIM_SETTLED) to external hospital and insurer system webhooks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
import httpx

log = logging.getLogger("event_bus")


@dataclass
class WebhookSubscription:
    tenant_id: str
    topic: str
    callback_url: str
    secret: str = "whsec_default"


@dataclass
class EventMessage:
    topic: str
    tenant_id: str
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: list[WebhookSubscription] = []

    def register_webhook(self, tenant_id: str, topic: str, callback_url: str, secret: str = "whsec_default") -> None:
        """Register an external system webhook callback."""
        sub = WebhookSubscription(tenant_id=tenant_id, topic=topic, callback_url=callback_url, secret=secret)
        self._subscriptions.append(sub)
        log.info("Registered webhook for tenant %s on topic '%s' -> %s", tenant_id, topic, callback_url)

    async def publish_event(self, topic: str, tenant_id: str, payload: dict) -> EventMessage:
        """Publish an event to all registered webhook subscribers asynchronously."""
        evt = EventMessage(topic=topic, tenant_id=tenant_id, payload=payload)
        log.info("EventBus published event [%s] for tenant %s", topic, tenant_id)

        # Dispatch webhooks asynchronously
        matching_subs = [
            s for s in self._subscriptions
            if s.topic == topic and (s.tenant_id == tenant_id or s.tenant_id == "*")
        ]

        for sub in matching_subs:
            asyncio.create_task(self._dispatch_webhook(sub, evt))

        return evt

    async def _dispatch_webhook(self, sub: WebhookSubscription, evt: EventMessage) -> bool:
        """Send HTTP POST callback to webhook URL."""
        headers = {
            "Content-Type": "application/json",
            "X-NoLoop-Event": evt.topic,
            "X-NoLoop-Signature": sub.secret,
        }
        body = {
            "topic": evt.topic,
            "tenantId": evt.tenant_id,
            "timestamp": evt.timestamp,
            "data": evt.payload,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(sub.callback_url, json=body, headers=headers)
                if res.status_code < 300:
                    log.info("Webhook delivered successfully to %s", sub.callback_url)
                    return True
        except Exception as err:
            log.warning("Webhook delivery failed for %s: %s", sub.callback_url, err)
        return False


# Global singleton event bus instance
event_bus = EventBus()
