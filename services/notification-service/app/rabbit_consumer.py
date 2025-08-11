# app/rabbit_consumer.py
import json
import aio_pika
from .settings import settings
from .logger import get_logger
from .schemas import EventEnvelope
from .websocket_manager import hub

log = get_logger("rabbit")

def _extract_tenant_workspace(envelope: dict) -> tuple[str | None, str | None]:
    meta = envelope.get("meta", {}) or {}
    tenant_id = meta.get("tenant_id")
    workspace_id = meta.get("workspace_id")
    subj = envelope.get("subject")
    if not workspace_id and isinstance(subj, str) and subj.startswith("workspace:"):
        workspace_id = subj.split(":", 1)[1]
    return tenant_id, workspace_id

async def consume_loop():
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=100)

    exchange = await channel.declare_exchange(
        settings.RABBITMQ_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(
        settings.RABBITMQ_QUEUE, durable=True, auto_delete=False
    )
    for rk in settings.RABBITMQ_BINDINGS:
        await queue.bind(exchange, rk)
        log.info(f"Bound to {rk}")

    async with queue.iterator() as it:
        async for message in it:
            async with message.process():
                try:
                    raw = json.loads(message.body.decode("utf-8"))
                    # If you added the normalizer, uncomment:
                    # from .normalizer import normalize_to_envelope
                    # envelope = normalize_to_envelope(raw)
                    envelope = raw
                    EventEnvelope.model_validate(envelope)
                    tenant_id, workspace_id = _extract_tenant_workspace(envelope)
                    if tenant_id and workspace_id:
                        await hub.send(tenant_id, workspace_id, envelope)
                    else:
                        log.info("Event missing tenant/workspace; dropped")
                except Exception as e:
                    log.exception(f"Failed to process message: {e}")

__all__ = ["consume_loop"]
