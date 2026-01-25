import asyncio
import pickle
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum

from ..logging_config import get_logger

logger = get_logger("insightbot.task_manager")


class TaskManagerState(Enum):
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


@dataclass
class PendingTask:
    """Serializable task for persistence."""
    func_name: str
    args: tuple
    kwargs: dict


class TaskManager:
    """Manages background tasks with graceful shutdown."""

    _instance: Optional["TaskManager"] = None
    PICKLE_PATH = Path(__file__).parent.parent / "data" / "pending_tasks.pkl"

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._state = TaskManagerState.RUNNING
        self._pending_queue: list[PendingTask] = []
        self._task_registry: dict[str, Callable] = {}

    @classmethod
    def get(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def register(self, name: str, func: Callable):
        """Register a function that can be persisted."""
        self._task_registry[name] = func

    def create_task(
        self,
        coro,
        *,
        name: str = None,
        persist_args: tuple = None,
        persist_kwargs: dict = None,
    ) -> Optional[asyncio.Task]:
        """Create a tracked background task."""
        if self._state == TaskManagerState.SHUTTING_DOWN:
            # Queue for persistence instead of running
            if name and name in self._task_registry:
                self._pending_queue.append(PendingTask(
                    func_name=name,
                    args=persist_args or (),
                    kwargs=persist_kwargs or {},
                ))
                logger.info(f"Task {name} queued for persistence (shutdown in progress)")
            return None

        if self._state == TaskManagerState.STOPPED:
            logger.warning(f"Task {name} dropped (manager stopped)")
            return None

        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self, timeout: float = 30.0):
        """Graceful shutdown: wait for tasks, then persist pending."""
        logger.info("TaskManager shutting down...")
        self._state = TaskManagerState.SHUTTING_DOWN

        # Wait for in-flight tasks
        if self._tasks:
            logger.info(f"Waiting for {len(self._tasks)} tasks to complete...")
            done, pending = await asyncio.wait(self._tasks, timeout=timeout)
            if pending:
                logger.warning(f"{len(pending)} tasks did not complete in time, cancelling...")
                for task in pending:
                    task.cancel()

        # Persist any queued tasks
        if self._pending_queue:
            self._save_pending()

        self._state = TaskManagerState.STOPPED
        logger.info("TaskManager shutdown complete")

    def _save_pending(self):
        """Save pending tasks to pickle file."""
        self.PICKLE_PATH.parent.mkdir(exist_ok=True)
        with open(self.PICKLE_PATH, "wb") as f:
            pickle.dump(self._pending_queue, f)
        logger.info(f"Saved {len(self._pending_queue)} pending tasks to {self.PICKLE_PATH}")

    async def load_and_run_pending(self):
        """Load and execute any persisted tasks from previous shutdown."""
        if not self.PICKLE_PATH.exists():
            logger.info("No pending tasks from previous session")
            return

        try:
            with open(self.PICKLE_PATH, "rb") as f:
                tasks = pickle.load(f)

            logger.info(f"Loading {len(tasks)} pending tasks from previous session")

            for task in tasks:
                if task.func_name in self._task_registry:
                    func = self._task_registry[task.func_name]
                    coro = func(*task.args, **task.kwargs)
                    self.create_task(coro, name=task.func_name)
                else:
                    logger.warning(f"Unknown task function: {task.func_name}")

            # Remove pickle file after loading
            self.PICKLE_PATH.unlink()

        except Exception as e:
            logger.error(f"Failed to load pending tasks: {e}")
            # Delete corrupted pickle file
            if self.PICKLE_PATH.exists():
                self.PICKLE_PATH.unlink()
