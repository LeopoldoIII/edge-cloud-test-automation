"""Linux process lifecycle manager and graceful shutdown handler for edge services."""

import json
import signal
import threading
from enum import Enum
from pathlib import Path
from types import FrameType
from typing import Any

from src.core.logger import get_logger
from src.simulators.edge_device_spool import EdgeDeviceSpool

logger = get_logger("edge_process_daemon")


class DaemonState(str, Enum):
    """Lifecycle states of the Linux edge process daemon."""

    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"


class EdgeProcessDaemon:
    """Simulates a containerized Linux edge daemon respecting POSIX signals (SIGTERM/SIGINT)."""

    def __init__(
        self,
        spool: EdgeDeviceSpool,
        checkpoint_path: Path | str = "/tmp/edge_spool_checkpoint.json",
    ) -> None:
        """Initializes the edge process daemon.

        Args:
            spool: Edge device spool instance.
            checkpoint_path: File system path for serializing uncommitted state on SIGTERM.
        """
        self.spool = spool
        self.checkpoint_path = Path(checkpoint_path)
        self.state = DaemonState.INITIALIZING
        self._stop_event = threading.Event()
        self._exit_code: int = 0

    def register_signal_handlers(self) -> None:
        """Registers handlers for SIGTERM and SIGINT."""
        signal.signal(signal.SIGTERM, self._handle_posix_signal)
        signal.signal(signal.SIGINT, self._handle_posix_signal)

    def _handle_posix_signal(self, signum: int, frame: FrameType | None) -> None:
        """Handles inbound termination signals from Docker/Kubernetes/systemd."""
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.warning(
            f"Received POSIX {sig_name}. Initiating graceful shutdown and state flush",
            extra={"device_id": self.spool.device_id},
        )
        self.shutdown_gracefully()

    def shutdown_gracefully(self) -> None:
        """Transitions daemon to DRAINING, flushes state to disk, and marks STOPPED."""
        self.state = DaemonState.DRAINING

        # Serialize in-memory unsynced queue to persistent disk checkpoint
        checkpoint_data: list[dict[str, Any]] = [
            {
                "item_id": item.item_id,
                "endpoint": item.endpoint,
                "payload": item.payload,
                "idempotency_key": item.idempotency_key,
                "retry_count": item.retry_count,
            }
            for item in self.spool.queue
        ]

        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2)

        logger.info(
            f"Persisted {len(checkpoint_data)} pending items to {self.checkpoint_path}",
            extra={"device_id": self.spool.device_id},
        )

        self.state = DaemonState.STOPPED
        self._stop_event.set()
        self._exit_code = 0

    def restore_from_checkpoint(self) -> int:
        """Restores unsynchronized items from persistent checkpoint file upon container restart.

        Returns:
            Count of restored items.
        """
        if not self.checkpoint_path.exists():
            return 0

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)

            restored_count = 0
            for item in checkpoint_data:
                self.spool.enqueue(endpoint=item["endpoint"], payload=item["payload"])
                restored_count += 1

            # Remove checkpoint after successful recovery to avoid replay
            self.checkpoint_path.unlink(missing_ok=True)
            self.state = DaemonState.RUNNING

            logger.info(
                f"Successfully restored {restored_count} items from checkpoint after process restart",
                extra={"device_id": self.spool.device_id},
            )
            return restored_count
        except Exception as exc:
            logger.error(f"Failed to restore checkpoint: {exc}")
            return 0

    @property
    def is_running(self) -> bool:
        """Checks if daemon is in RUNNING state."""
        return self.state == DaemonState.RUNNING and not self._stop_event.is_set()
