import pytest

from mplacas.events.bus import DomainEvent, EventBus


@pytest.mark.asyncio
async def test_event_bus_delivers_to_subscriber_once() -> None:
    received: list[str] = []

    async def handler(event: DomainEvent) -> None:
        received.append(str(event.payload["job_id"]))

    bus = EventBus()
    bus.subscribe("collection.completed", handler)
    bus.subscribe("collection.completed", handler)

    await bus.publish(DomainEvent("collection.completed", {"job_id": "abc"}))

    assert received == ["abc"]
