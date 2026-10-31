"""Resilience test suite validating Linux edge process lifecycles and graceful shutdown."""

import signal
from pathlib import Path
import pytest

from src.core.http_client import ResilientHttpClient
from src.simulators.edge_device_spool import EdgeDeviceSpool
from src.simulators.edge_process_daemon import DaemonState, EdgeProcessDaemon


@pytest.mark.resilience
class TestProcessLifecycle:
    """Test suite ensuring SIGTERM triggers state persistence without telemetry loss."""

    def test_sigterm_graceful_shutdown_and_checkpoint(
        self,
        resilient_client: ResilientHttpClient,
        tmp_path: Path,
    ) -> None:
        """Verifies that receiving SIGTERM flushes uncommitted items to checkpoint disk storage."""
        checkpoint_file = tmp_path / "spool_chk.json"
        spool = EdgeDeviceSpool(device_id="edge-daemon-01", client=resilient_client)

        # Enqueue items before shutdown
        spool.enqueue("/api/v1/telemetry", {"batch": "A"})
        spool.enqueue("/api/v1/telemetry", {"batch": "B"})

        daemon = EdgeProcessDaemon(spool=spool, checkpoint_path=checkpoint_file)
        daemon.state = DaemonState.RUNNING

        # Simulate inbound POSIX SIGTERM signal
        daemon._handle_posix_signal(signal.SIGTERM, None)

        assert daemon.state == DaemonState.STOPPED
        assert checkpoint_file.exists()

    def test_daemon_restart_and_state_recovery(
        self,
        resilient_client: ResilientHttpClient,
        tmp_path: Path,
    ) -> None:
        """Verifies that restarted daemon restores pending items and clears checkpoint file."""
        checkpoint_file = tmp_path / "spool_chk.json"

        # 1. Daemon 1 enqueues and shuts down
        spool_old = EdgeDeviceSpool(device_id="edge-daemon-02", client=resilient_client)
        spool_old.enqueue("/api/v1/telemetry", {"batch": "restore_1"})
        spool_old.enqueue("/api/v1/telemetry", {"batch": "restore_2"})

        daemon_old = EdgeProcessDaemon(spool=spool_old, checkpoint_path=checkpoint_file)
        daemon_old.shutdown_gracefully()
        assert checkpoint_file.exists()

        # 2. Daemon 2 boots up in a new container process
        spool_new = EdgeDeviceSpool(device_id="edge-daemon-02", client=resilient_client)
        daemon_new = EdgeProcessDaemon(spool=spool_new, checkpoint_path=checkpoint_file)

        restored = daemon_new.restore_from_checkpoint()
        assert restored == 2
        assert spool_new.pending_count == 2
        assert not checkpoint_file.exists()  # Checkpoint cleared to avoid replay
        assert daemon_new.state == DaemonState.RUNNING

    def test_restore_nonexistent_checkpoint_noop(
        self,
        resilient_client: ResilientHttpClient,
        tmp_path: Path,
    ) -> None:
        """Verifies restoring when no checkpoint exists safely returns 0."""
        spool = EdgeDeviceSpool(device_id="edge-daemon-03", client=resilient_client)
        daemon = EdgeProcessDaemon(spool=spool, checkpoint_path=tmp_path / "nonexistent.json")
        assert daemon.restore_from_checkpoint() == 0

    def test_daemon_signal_registration_and_running_property(
        self,
        resilient_client: ResilientHttpClient,
        tmp_path: Path,
    ) -> None:
        """Verifies signal handler registration and is_running status check."""
        spool = EdgeDeviceSpool(device_id="edge-daemon-04", client=resilient_client)
        daemon = EdgeProcessDaemon(spool=spool, checkpoint_path=tmp_path / "chk.json")
        daemon.register_signal_handlers()

        daemon.state = DaemonState.RUNNING
        assert daemon.is_running is True

        daemon.shutdown_gracefully()
        assert daemon.is_running is False
