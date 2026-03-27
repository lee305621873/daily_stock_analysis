# -*- coding: utf-8 -*-
"""
Async task queue for stock screener jobs.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from api.v1.schemas.stocks import (
    MarketType,
    ScreenerScanRequest,
    ScreenerScanResultItem,
    ScreenerScanResponse,
    ScreenerTaskAccepted,
    ScreenerTaskStatusEnum,
)
from src.services.stock_screener_service import StockScreenerService

if TYPE_CHECKING:
    from asyncio import Queue as AsyncQueue

logger = logging.getLogger(__name__)


@dataclass
class ScreenerTaskRecord:
    task_id: str
    request: ScreenerScanRequest
    status: ScreenerTaskStatusEnum = ScreenerTaskStatusEnum.PENDING
    progress: int = 0
    scanned_count: int = 0
    total_count: int = 0
    matched_count: int = 0
    message: Optional[str] = None
    result: Optional[ScreenerScanResponse] = None
    full_results: Optional[List[ScreenerScanResultItem]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self, include_result: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "task_id": self.task_id,
            "market": self.request.market.value if isinstance(self.request.market, MarketType) else self.request.market,
            "status": self.status.value,
            "progress": self.progress,
            "scanned_count": self.scanned_count,
            "total_count": self.total_count,
            "matched_count": self.matched_count,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
        if include_result:
            payload["result"] = self.result.model_dump() if self.result else None
        return payload

    def copy(self) -> "ScreenerTaskRecord":
        return ScreenerTaskRecord(
            task_id=self.task_id,
            request=self.request.model_copy(deep=True),
            status=self.status,
            progress=self.progress,
            scanned_count=self.scanned_count,
            total_count=self.total_count,
            matched_count=self.matched_count,
            message=self.message,
            result=self.result.model_copy(deep=True) if self.result else None,
            full_results=None,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


class StockScreenerTaskQueue:
    _instance: Optional["StockScreenerTaskQueue"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 1):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._tasks: Dict[str, ScreenerTaskRecord] = {}
        self._futures: Dict[str, Future] = {}
        self._subscribers: List["AsyncQueue"] = []
        self._subscribers_lock = threading.Lock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._data_lock = threading.RLock()
        self._max_history = 20
        self._initialized = True
        logger.info("[ScreenerTaskQueue] initialized, max_workers=%s", max_workers)

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="stock_screener_task",
            )
        return self._executor

    def submit_task(self, request: ScreenerScanRequest) -> ScreenerTaskAccepted:
        task_id = uuid.uuid4().hex
        task = ScreenerTaskRecord(
            task_id=task_id,
            request=request.model_copy(deep=True),
            message="选股任务已加入后台队列",
        )
        with self._data_lock:
            self._tasks[task_id] = task
            self._futures[task_id] = self.executor.submit(self._execute_task, task_id, request.model_copy(deep=True))
        self._broadcast_event("task_created", task.to_dict())
        return ScreenerTaskAccepted(task_id=task_id, message=task.message or "选股任务已提交")

    def get_task(self, task_id: str) -> Optional[ScreenerTaskRecord]:
        with self._data_lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None

    def list_pending_tasks(self) -> List[ScreenerTaskRecord]:
        with self._data_lock:
            return [
                task.copy()
                for task in self._tasks.values()
                if task.status in (ScreenerTaskStatusEnum.PENDING, ScreenerTaskStatusEnum.PROCESSING)
            ]

    def subscribe(self, queue: "AsyncQueue") -> None:
        with self._subscribers_lock:
            self._subscribers.append(queue)
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    self._main_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass

    def unsubscribe(self, queue: "AsyncQueue") -> None:
        with self._subscribers_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _execute_task(self, task_id: str, request: ScreenerScanRequest) -> Optional[ScreenerScanResponse]:
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.status = ScreenerTaskStatusEnum.PROCESSING
            task.started_at = datetime.now()
            task.progress = 1
            task.message = "正在准备股票池..."
            snapshot = task.to_dict()
        self._broadcast_event("task_started", snapshot)

        try:
            service = StockScreenerService()

            def _capture_full_results(items: List[ScreenerScanResultItem]) -> None:
                with self._data_lock:
                    task_snapshot = self._tasks.get(task_id)
                    if task_snapshot is not None:
                        task_snapshot.full_results = list(items)

            result = service.scan(
                request,
                progress_callback=lambda scanned, total, matched, message: self._update_progress(
                    task_id,
                    scanned,
                    total,
                    matched,
                    message,
                ),
                full_results_callback=_capture_full_results,
            )
            with self._data_lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return result
                task.status = ScreenerTaskStatusEnum.COMPLETED
                task.progress = 100
                task.completed_at = datetime.now()
                task.result = result
                task.message = f"选股完成，共命中 {result.total} 条"
                task.matched_count = result.total
                snapshot = task.to_dict()
            self._broadcast_event("task_completed", snapshot)
            self._cleanup_old_tasks()
            return result
        except Exception as exc:
            logger.error("[ScreenerTaskQueue] task failed: %s", exc, exc_info=True)
            with self._data_lock:
                task = self._tasks.get(task_id)
                if task is None:
                    return None
                task.status = ScreenerTaskStatusEnum.FAILED
                task.completed_at = datetime.now()
                task.error = str(exc)[:300]
                task.message = f"选股失败: {str(exc)[:80]}"
                snapshot = task.to_dict()
            self._broadcast_event("task_failed", snapshot)
            self._cleanup_old_tasks()
            return None

    def get_task_export_items(self, task_id: str, scope: str = "all") -> Optional[List[ScreenerScanResultItem]]:
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != ScreenerTaskStatusEnum.COMPLETED or task.result is None:
                return None
            if scope == "page":
                return list(task.result.results)
            if task.full_results:
                return list(task.full_results)
            return list(task.result.results)

    def _update_progress(
        self,
        task_id: str,
        scanned: int,
        total: int,
        matched: int,
        message: str,
    ) -> None:
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.scanned_count = scanned
            task.total_count = total
            task.matched_count = matched
            if total > 0:
                task.progress = min(99, max(task.progress, int(scanned * 100 / total)))
            task.message = message
            snapshot = task.to_dict()

        should_broadcast = (
            scanned == total
            or scanned <= 5
            or total <= 50
            or scanned % 50 == 0
        )
        if should_broadcast:
            self._broadcast_event("task_progress", snapshot)

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        event = {"type": event_type, "data": data}
        with self._subscribers_lock:
            subscribers = self._subscribers.copy()
            loop = self._main_loop

        if not subscribers or loop is None:
            return

        for queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[ScreenerTaskQueue] broadcast skipped: %s", exc)

    def _cleanup_old_tasks(self) -> None:
        with self._data_lock:
            if len(self._tasks) <= self._max_history:
                return
            removable = sorted(
                [
                    task for task in self._tasks.values()
                    if task.status in (ScreenerTaskStatusEnum.COMPLETED, ScreenerTaskStatusEnum.FAILED)
                ],
                key=lambda item: item.created_at,
            )
            to_remove = len(self._tasks) - self._max_history
            for task in removable[:to_remove]:
                self._tasks.pop(task.task_id, None)
                self._futures.pop(task.task_id, None)


def get_stock_screener_task_queue() -> StockScreenerTaskQueue:
    return StockScreenerTaskQueue()
