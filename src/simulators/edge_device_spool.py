"""Local persistent spool manager simulating offline-first edge storage and synchronization."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from src.core.http_client import ResilientHttpClient
from src.core.logger import get_logger

logger = get_logger("edge_device_spool")


@dataclass
class SpoolItem:
    """Represents a queued edge record stored in local storage."""

    item_id: str
    endpoint: str
    payload: dict[str, Any]
    idempotency_key: str
    queued_at: float = field(default_factory=time.time)
    retry_count: int = 0


class EdgeDeviceSpool:
    """Manages local storage queue for offline edge devices and draining across intermittent uplinks."""

    def __init__(self, device_id: str, client: ResilientHttpClient) -> None:
        """Initializes the edge device spooler.

        Args:
            device_id: Unique hardware or station identifier.
            client: Resilient HTTP client configured for transmission.
        """
        self.device_id = device_id
        self.client = client
        self.queue: list[SpoolItem] = []
        self.synced_items: list[SpoolItem] = []

    def enqueue(self, endpoint: str, payload: dict[str, Any]) -> str:
        """Appends a new payload to the local offline spool.

        Args:
            endpoint: Target API path.
            payload: JSON payload to transmit.

        Returns:
            Unique idempotency key assigned to this queued item.
        """
        idempotency_key = f"spool-{self.device_id}-{uuid.uuid4()}"
        item = SpoolItem(
            item_id=str(uuid.uuid4()),
            endpoint=endpoint,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        self.queue.append(item)
        logger.info(
            "Item buffered to local edge spool",
            extra={"device_id": self.device_id, "idempotency_key": idempotency_key},
        )
        return idempotency_key

    @property
    def pending_count(self) -> int:
        """Returns the number of unsynchronized items in the spool."""
        return len(self.queue)

    def drain_all(
        self, custom_dispatcher: Callable[[str, dict[str, Any], str], bool] | None = None
    ) -> int:
        """Attempts to synchronize and flush all buffered spool items to the cloud.

        Args:
            custom_dispatcher: Optional dispatch callback (endpoint, payload, idempotency_key).
                               If omitted, dispatches via ResilientHttpClient.

        Returns:
            Count of successfully synchronized items.
        """
        success_count = 0
        remaining_queue: list[SpoolItem] = []

        for item in self.queue:
            try:
                if custom_dispatcher:
                    success = custom_dispatcher(item.endpoint, item.payload, item.idempotency_key)
                else:
                    resp = self.client.request(
                        method="POST",
                        path=item.endpoint,
                        idempotency_key=item.idempotency_key,
                        json_data=item.payload,
                    )
                    success = resp.status_code in {200, 201}

                if success:
                    self.synced_items.append(item)
                    success_count += 1
                else:
                    item.retry_count += 1
                    remaining_queue.append(item)
            except Exception as exc:
                logger.error(
                    f"Failed to synchronize spooled item: {exc}",
                    extra={"device_id": self.device_id, "idempotency_key": item.idempotency_key},
                )
                item.retry_count += 1
                remaining_queue.append(item)

        self.queue = remaining_queue
        return success_count
