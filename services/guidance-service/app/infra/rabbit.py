# app/infra/rabbit.py
from __future__ import annotations

import json
import asyncio
import logging
from typing import Optional, Dict

import aio_pika
from aio_pika import ExchangeType, DeliveryMode

from app.config import settings
from libs.raina_common.events import rk, Service, Version

logger = logging.getLogger("guidance.infra.rabbit")

class RabbitPublisher:
    """
    Async publisher that emits ONLY versioned routing keys:
        <org>.guidance.<event>.<version>
    Reuses a robust connection + channel + exchange.
    """
    def __init__(self, url: Optional[str] = None, exchange_name: Optional[str] = None):
        self.url = url or settings.RABBITMQ_URL
        self.exchange_name = exchange_name or settings.RABBITMQ_EXCHANGE
        self._conn: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None
        self._exchange: Optional[aio_pika.abc.AbstractExchange] = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._exchange:
            return
        async with self._lock:
            if self._exchange:
                return
            logger.info("Rabbit: connecting...")
            self._conn = await aio_pika.connect_robust(self.url)
            self._channel = await self._conn.channel()
            await self._channel.set_qos(prefetch_count=32)
            self._exchange = await self._channel.declare_exchange(
                self.exchange_name, ExchangeType.TOPIC, durable=True
            )
            logger.info("Rabbit: connected and exchange declared", extra={"exchange": self.exchange_name})

    async def publish_v1(
        self,
        *,
        org: str,
        event: str,
        payload: dict,
        headers: Optional[Dict[str, str]] = None,
        version: str = Version.V1.value,
    ) -> None:
        """
        Publish a versioned Guidance event as persistent JSON.
        Routing key: <org>.guidance.<event>.<version>
        """
        await self._ensure()
        assert self._exchange is not None

        routing_key = rk(org=org, service=Service.GUIDANCE, event=event, version=version)
        msg = aio_pika.Message(
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers=headers or {},
        )
        await self._exchange.publish(msg, routing_key=routing_key)
        logger.info("Rabbit: event published", extra={"routing_key": routing_key})

    async def close(self) -> None:
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
        finally:
            if self._conn and not self._conn.is_closed:
                await self._conn.close()

# Module-level singleton for convenience
publisher = RabbitPublisher()

# Backwards-incompatible: remove legacy API if present anywhere
async def publish(routing_key: str, message: dict):  # pragma: no cover
    raise RuntimeError("Use publish_v1(event=..., payload=..., org=...) instead.")

# Convenience wrapper matching the rest of Raina services
async def publish_event_v1(
    *,
    event: str,
    payload: dict,
    org: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> None:
    await publisher.publish_v1(
        org=org or settings.EVENTS_ORG,
        event=event,
        payload=payload,
        headers=headers,
    )
