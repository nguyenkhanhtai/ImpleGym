"""Progress tracking and real-time state management for problem synchronization."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any
from pydantic import BaseModel


class SyncProgressState(BaseModel):
    """Data contract representing the real-time state of a synchronization job."""

    is_running: bool = False
    stage: str = "idle"  # idle, git_clone_pull, scanning, syncing_problems, completed, error, cancelled
    current: int = 0
    total: int = 0
    current_slug: str = ""
    current_category: str = ""
    synced_count: int = 0
    percent: float = 0.0
    message: str = "Idle"
    started_at: float | None = None
    completed_at: float | None = None
    duration_seconds: float = 0.0
    error: str | None = None


class SyncProgressTracker:
    """Singleton tracker to manage and broadcast synchronization progress events."""

    def __init__(self) -> None:
        self._state = SyncProgressState()
        self._listeners: list[asyncio.Queue[dict[str, Any]]] = []
        self._cancel_requested = False

    def get_state(self) -> SyncProgressState:
        """Get the current progress snapshot."""
        if self._state.is_running and self._state.started_at:
            self._state.duration_seconds = round(time.time() - self._state.started_at, 1)
        return self._state

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_requested

    def request_cancel(self) -> None:
        """Request the active synchronization task to stop gracefully."""
        self._cancel_requested = True
        self.update(stage="cancelled", message="Cancellation requested...")

    def reset(self) -> None:
        """Reset the sync progress tracker state."""
        self._state = SyncProgressState()
        self._cancel_requested = False

    def start(self, total: int = 0, message: str = "Starting synchronization...") -> None:
        """Mark synchronization as started."""
        self._cancel_requested = False
        now = time.time()
        self._state = SyncProgressState(
            is_running=True,
            stage="git_clone_pull",
            current=0,
            total=total,
            current_slug="",
            current_category="",
            synced_count=0,
            percent=0.0,
            message=message,
            started_at=now,
            completed_at=None,
            duration_seconds=0.0,
            error=None,
        )
        self._broadcast()

    def update(
        self,
        *,
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        current_slug: str | None = None,
        current_category: str | None = None,
        synced_count: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update progress state and notify all connected listeners."""
        if stage is not None:
            self._state.stage = stage
        if total is not None:
            self._state.total = total
        if current is not None:
            self._state.current = current
        if current_slug is not None:
            self._state.current_slug = current_slug
        if current_category is not None:
            self._state.current_category = current_category
        if synced_count is not None:
            self._state.synced_count = synced_count
        if message is not None:
            self._state.message = message

        if self._state.started_at:
            self._state.duration_seconds = round(time.time() - self._state.started_at, 1)

        if self._state.total > 0:
            self._state.percent = round(min(100.0, (self._state.current / self._state.total) * 100.0), 1)
        else:
            self._state.percent = 0.0

        self._broadcast()

    def complete(self, synced_count: int, message: str | None = None) -> None:
        """Mark synchronization as successfully finished."""
        now = time.time()
        self._state.is_running = False
        self._state.stage = "completed"
        self._state.current = self._state.total
        self._state.percent = 100.0
        self._state.synced_count = synced_count
        self._state.completed_at = now
        if self._state.started_at:
            self._state.duration_seconds = round(now - self._state.started_at, 1)
        self._state.message = message or f"Successfully synchronized {synced_count} problems!"
        self._broadcast()

    def fail(self, error_message: str) -> None:
        """Mark synchronization as failed."""
        now = time.time()
        self._state.is_running = False
        self._state.stage = "error"
        self._state.error = error_message
        self._state.completed_at = now
        if self._state.started_at:
            self._state.duration_seconds = round(now - self._state.started_at, 1)
        self._state.message = f"Sync failed: {error_message}"
        self._broadcast()

    def _broadcast(self) -> None:
        """Broadcast state dict to all active queues."""
        data = self._state.model_dump(mode="json")
        for q in list(self._listeners):
            try:
                q.put_nowait(data)
            except Exception:
                pass

    async def event_generator(self) -> AsyncGenerator[str, None]:
        """Async generator yielding Server-Sent Events (SSE) formatted progress updates."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._listeners.append(q)
        try:
            # Yield initial state immediately
            initial_data = self.get_state().model_dump_json()
            yield f"data: {initial_data}\n\n"

            while True:
                data = await q.get()
                yield f"data: {json.dumps(data)}\n\n"
                if not data.get("is_running", True) and data.get("stage") in ("completed", "error", "cancelled"):
                    break
        finally:
            if q in self._listeners:
                self._listeners.remove(q)


# Global singleton tracker instance
sync_progress_tracker = SyncProgressTracker()
