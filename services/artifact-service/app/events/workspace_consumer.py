from __future__ import annotations

import asyncio
import json
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import aio_pika

from ..config import settings
from ..dal import artifact_dal as dal
from ..models.artifact import WorkspaceSnapshot

# Common event RK builder
from libs.raina_common.events import rk, Service, Version

log = logging.getLogger("app.events.workspace_consumer")

# Build the three routing keys we care about (created/updated/deleted)
_RK_CREATED = rk(settings.events_org, Service.WORKSPACE, "created")
_RK_UPDATED = rk(settings.events_org, Service.WORKSPACE, "updated")
_RK_DELETED = rk(settings.events_org, Service.WORKSPACE, "deleted")


async def _handle_message_created(db: AsyncIOMotorDatabase, payload: dict) -> None:
    data = payload.get("workspace", payload)
    if "_id" not in data and "id" in data:
        data = {**data, "_id": data["id"]}
    ws = WorkspaceSnapshot.model_validate(data)

    # Idempotent parent creation
    if await dal.get_parent_doc(db, ws.id):
        log.info("Parent already exists for workspace_id=%s", ws.id)
        return

    created = await dal.create_parent_doc(db, ws)
    log.info("Created WorkspaceArtifactsDoc: workspace_id=%s, doc_id=%s", ws.id, created.id)


async def _handle_message_updated(db: AsyncIOMotorDatabase, payload: dict) -> None:
    data = payload.get("workspace", payload)
    if "_id" not in data and "id" in data:
        data = {**data, "_id": data["id"]}
    ws = WorkspaceSnapshot.model_validate(data)
    await dal.refresh_workspace_snapshot(db, ws)
    log.info("Refreshed workspace snapshot for workspace_id=%s", ws.id)


async def _handle_message_deleted(db: AsyncIOMotorDatabase, payload: dict) -> None:
    data = payload.get("workspace", payload)
    wid = data.get("_id") or data.get("id")
    if not wid:
        log.error("workspace.deleted payload missing id/_id: %s", payload)
        return
    ok = await dal.delete_parent_doc(db, wid)
    log.info("Deleted parent doc for workspace_id=%s (ok=%s)", wid, ok)


async def run_workspace_created_consumer(db: AsyncIOMotorDatabase, shutdown_event: asyncio.Event) -> None:
    """
    Long-running consumer for workspace lifecycle events.
    Reconnects on failure. Stops when shutdown_event is set.
    """
    queue_name = settings.consumer_queue_workspace  # durable named queue by default (can be "" for anonymous)

    while not shutdown_event.is_set():
        try:
            log.info("Connecting to RabbitMQ at %s ...", settings.rabbitmq_uri)
            connection = await aio_pika.connect_robust(settings.rabbitmq_uri)
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=16)

                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                )

                queue = await channel.declare_queue(
                    queue_name or "",  # empty => anonymous auto-delete queue
                    durable=True if queue_name else False,
                    auto_delete=False if queue_name else True,
                )

                # Bind to the three versioned keys
                await queue.bind(exchange, routing_key=_RK_CREATED)
                await queue.bind(exchange, routing_key=_RK_UPDATED)
                await queue.bind(exchange, routing_key=_RK_DELETED)

                log.info(
                    "Consuming queue=%s exchange=%s rks=[%s, %s, %s]",
                    queue.name, settings.rabbitmq_exchange, _RK_CREATED, _RK_UPDATED, _RK_DELETED
                )

                async with queue.iterator() as q:
                    async for message in q:
                        if shutdown_event.is_set():
                            break
                        async with message.process(requeue=False):
                            try:
                                payload = json.loads(message.body.decode("utf-8"))
                            except Exception as e:
                                log.exception("Invalid JSON: %s", e)
                                continue

                            rk_in = message.routing_key
                            if rk_in == _RK_CREATED:
                                await _handle_message_created(db, payload)
                            elif rk_in == _RK_UPDATED:
                                await _handle_message_updated(db, payload)
                            elif rk_in == _RK_DELETED:
                                await _handle_message_deleted(db, payload)
                            else:
                                log.warning("Unhandled routing key: %s", rk_in)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.exception("workspace consumer error; retrying in 3s: %s", e)
            await asyncio.sleep(3.0)

    log.info("workspace consumer stopped")
