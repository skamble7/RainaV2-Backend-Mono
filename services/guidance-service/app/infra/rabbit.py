import json, asyncio
import aio_pika
from app.config import settings

class RabbitPublisher:
    def __init__(self, url: str | None = None):
        self.url = url or settings.RABBITMQ_URL
        self._conn = None

    async def connect(self):
        if not self._conn:
            self._conn = await aio_pika.connect_robust(self.url)

    async def publish(self, routing_key: str, message: dict):
        await self.connect()
        channel = await self._conn.channel()
        exchange = await channel.declare_exchange("raina.events", aio_pika.ExchangeType.TOPIC, durable=True)
        await exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode("utf-8")),
            routing_key=routing_key
        )

    async def close(self):
        if self._conn:
            await self._conn.close()
