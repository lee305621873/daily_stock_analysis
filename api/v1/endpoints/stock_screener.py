# -*- coding: utf-8 -*-
"""Technical stock screener endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.stocks import (
    FormulaFunctionMeta,
    FormulaValidationRequest,
    FormulaValidationResponse,
    IndicatorMeta,
    MarketType,
    ScreenerBoardConstituentResponse,
    ScreenerBoardOption,
    ScreenerBoardPreview,
    ScreenerBoardType,
    ScreenerScanRequest,
    ScreenerScanResponse,
    ScreenerScopeOption,
    ScreenerTaskAccepted,
    ScreenerTaskStatusResponse,
)
from src.services.stock_screener_service import StockScreenerService
from src.services.stock_screener_task_queue import get_stock_screener_task_queue

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/scopes",
    response_model=list[ScreenerScopeOption],
    responses={
        200: {"description": "Scope metadata"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Get screener scan scope metadata",
)
def list_scope_catalog(market: MarketType | None = None):
    try:
        service = StockScreenerService()
        return service.scope_catalog(market)
    except Exception as exc:
        logger.error("Failed to load stock screener scope catalog: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载选股扫描范围失败"},
        )


@router.get(
    "/boards",
    response_model=list[ScreenerBoardOption],
    responses={
        200: {"description": "Board metadata"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Get screener board catalog",
)
def list_board_catalog(market: MarketType, board_type: ScreenerBoardType):
    try:
        service = StockScreenerService()
        return service.board_catalog(market, board_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Failed to load stock screener board catalog: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载板块目录失败"},
        )


@router.get(
    "/boards/preview",
    response_model=ScreenerBoardPreview,
    responses={
        200: {"description": "Board preview"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Preview screener board constituents",
)
def preview_board_constituents(
    market: MarketType,
    board_type: ScreenerBoardType,
    board_name: str,
    limit: int = 20,
):
    try:
        service = StockScreenerService()
        return service.board_preview(market, board_type, board_name, limit=limit)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Failed to preview stock screener board constituents: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载板块成分股预览失败"},
        )


@router.get(
    "/boards/constituents",
    response_model=ScreenerBoardConstituentResponse,
    responses={
        200: {"description": "Full board constituents"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Get full screener board constituents",
)
def list_board_constituents(
    market: MarketType,
    board_type: ScreenerBoardType,
    board_name: str,
):
    try:
        service = StockScreenerService()
        return service.board_constituents(market, board_type, board_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Failed to load full stock screener board constituents: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载完整板块成分股失败"},
        )


@router.get(
    "/indicators",
    response_model=list[IndicatorMeta],
    responses={
        200: {"description": "Indicator metadata"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Get screener indicator metadata",
)
def list_indicator_catalog():
    try:
        service = StockScreenerService()
        return service.indicator_catalog()
    except Exception as exc:
        logger.error("Failed to load stock screener indicator catalog: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载选股指标元数据失败"},
        )


@router.get(
    "/formula/functions",
    response_model=list[FormulaFunctionMeta],
    responses={
        200: {"description": "Formula function metadata"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Get formula function catalog",
)
def list_formula_functions():
    try:
        service = StockScreenerService()
        return service.formula_function_catalog()
    except Exception as exc:
        logger.error("Failed to load stock formula function catalog: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载公式函数元数据失败"},
        )


@router.post(
    "/formula/validate",
    response_model=FormulaValidationResponse,
    responses={
        200: {"description": "Validation completed"},
        400: {"description": "Invalid formula", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Validate screener formula",
)
def validate_formula(body: FormulaValidationRequest):
    try:
        service = StockScreenerService()
        return service.validate_formula(body.formula)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Stock formula validation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"公式校验失败: {exc}"},
        )


@router.post(
    "/scan",
    response_model=ScreenerScanResponse | ScreenerTaskAccepted,
    responses={
        200: {"description": "Scan completed"},
        202: {"description": "Background task accepted", "model": ScreenerTaskAccepted},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Run technical stock screening",
)
def run_screener_scan(body: ScreenerScanRequest):
    try:
        should_run_async = body.async_mode or (body.market == MarketType.CN and not body.codes)
        if should_run_async:
            task = get_stock_screener_task_queue().submit_task(body.model_copy(update={"async_mode": True}))
            return JSONResponse(status_code=202, content=task.model_dump())

        service = StockScreenerService()
        return service.scan(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Stock screener scan failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"选股扫描失败: {exc}"},
        )


@router.get(
    "/tasks/stream",
    responses={
        200: {"description": "SSE event stream", "content": {"text/event-stream": {}}},
    },
    summary="Stream screener task updates",
)
async def stream_screener_tasks():
    async def event_generator():
        task_queue = get_stock_screener_task_queue()
        event_queue: asyncio.Queue = asyncio.Queue()

        yield _format_sse_event("connected", {"message": "Connected to screener task stream"})

        pending_tasks = task_queue.list_pending_tasks()
        for task in pending_tasks:
            yield _format_sse_event("task_created", task.to_dict())

        task_queue.subscribe(event_queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    yield _format_sse_event(event["type"], event["data"])
                except asyncio.TimeoutError:
                    yield _format_sse_event("heartbeat", {"timestamp": datetime.now().isoformat()})
        except asyncio.CancelledError:
            pass
        finally:
            task_queue.unsubscribe(event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/tasks/{task_id}",
    response_model=ScreenerTaskStatusResponse,
    responses={
        200: {"description": "Task status"},
        404: {"description": "Task not found", "model": ErrorResponse},
    },
    summary="Get screener task status",
)
def get_screener_task(task_id: str):
    task = get_stock_screener_task_queue().get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "task_not_found", "message": f"选股任务不存在: {task_id}"},
        )
    return ScreenerTaskStatusResponse(**task.to_dict(include_result=True))


def _format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
