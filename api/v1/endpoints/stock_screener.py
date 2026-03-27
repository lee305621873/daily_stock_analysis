# -*- coding: utf-8 -*-
"""Technical stock screener endpoints."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.stocks import (
    FormulaFunctionMeta,
    FormulaValidationRequest,
    FormulaValidationResponse,
    IndicatorMeta,
    MarketType,
    ScreenerExportFormat,
    ScreenerExportScope,
    ScreenerBoardConstituentResponse,
    ScreenerBoardOption,
    ScreenerBoardPreview,
    ScreenerBoardType,
    ScreenerRowsExportRequest,
    ScreenerScanRequest,
    ScreenerScanResultItem,
    ScreenerScanResponse,
    ScreenerFormulaTemplate,
    ScreenerFormulaTemplateDeleteResponse,
    ScreenerFormulaTemplateUpsertRequest,
    ScreenerScopeOption,
    ScreenerTaskAccepted,
    ScreenerTaskStatusEnum,
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
    limit: int = 0,
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


@router.get(
    "/formula/templates",
    response_model=list[ScreenerFormulaTemplate],
    responses={
        200: {"description": "Custom formula templates"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="List screener custom formula templates",
)
def list_formula_templates():
    try:
        service = StockScreenerService()
        return service.list_formula_templates()
    except Exception as exc:
        logger.error("Failed to load stock formula templates: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "加载我的公式模板失败"},
        )


@router.post(
    "/formula/templates",
    response_model=ScreenerFormulaTemplate,
    responses={
        200: {"description": "Template saved"},
        400: {"description": "Invalid request", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Create or update screener custom formula template",
)
def upsert_formula_template(body: ScreenerFormulaTemplateUpsertRequest):
    try:
        service = StockScreenerService()
        return service.upsert_formula_template(
            label=body.label,
            value=body.value,
            template_id=body.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("Failed to save stock formula template: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "保存我的公式模板失败"},
        )


@router.delete(
    "/formula/templates/{template_id}",
    response_model=ScreenerFormulaTemplateDeleteResponse,
    responses={
        200: {"description": "Template deleted"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Delete screener custom formula template",
)
def delete_formula_template(template_id: str):
    try:
        service = StockScreenerService()
        deleted = service.delete_formula_template(template_id)
        return ScreenerFormulaTemplateDeleteResponse(id=template_id, deleted=deleted)
    except Exception as exc:
        logger.error("Failed to delete stock formula template: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "删除我的公式模板失败"},
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
        # Scope-based scans (without explicit code list) can be large and may exceed
        # synchronous HTTP timeout budgets; default those requests to background tasks.
        scope_key = str((body.scope or "")).strip().lower()
        has_scope_universe = bool(scope_key and scope_key != "custom_pool") or bool((body.board_name or "").strip())
        should_run_async = body.async_mode or (
            not body.codes and (body.market == MarketType.CN or has_scope_universe)
        )
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


@router.get(
    "/tasks/{task_id}/export",
    responses={
        200: {"description": "Exported file stream"},
        404: {"description": "Task not found", "model": ErrorResponse},
        409: {"description": "Task not completed", "model": ErrorResponse},
    },
    summary="Export screener task results as CSV/XLSX",
)
def export_screener_task_results(
    task_id: str,
    format: ScreenerExportFormat = Query(default=ScreenerExportFormat.XLSX),
    scope: ScreenerExportScope = Query(default=ScreenerExportScope.ALL),
):
    task_queue = get_stock_screener_task_queue()
    task = task_queue.get_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "task_not_found", "message": f"选股任务不存在: {task_id}"},
        )
    if task.status != ScreenerTaskStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail={"error": "task_not_completed", "message": "任务尚未完成，暂时无法导出"},
        )

    items = task_queue.get_task_export_items(task_id, scope=scope.value)
    if items is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "task_export_unavailable", "message": "任务结果暂不可导出，请稍后重试"},
        )
    filename = f"stock-screener-{task_id[:8]}-{scope.value}"
    return _build_export_response(items, format, filename)


@router.post(
    "/export/rows",
    responses={
        200: {"description": "Exported file stream"},
        400: {"description": "Invalid request", "model": ErrorResponse},
    },
    summary="Export provided screener rows as CSV/XLSX",
)
def export_screener_rows(body: ScreenerRowsExportRequest):
    filename = body.filename or "stock-screener-rows"
    return _build_export_response(body.items, body.format, filename)


_EXPORT_HEADERS = ["代码", "名称", "最新价", "热度", "命中条件/公式", "板块", "数据源"]


def _build_export_response(
    items: list[ScreenerScanResultItem],
    export_format: ScreenerExportFormat,
    filename_prefix: str,
) -> StreamingResponse:
    if export_format == ScreenerExportFormat.CSV:
        payload = _to_csv_bytes(items)
        suffix = "csv"
        media_type = "text/csv; charset=utf-8"
    else:
        payload = _to_xlsx_bytes(items)
        suffix = "xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in filename_prefix).strip("-")
    if not safe_prefix:
        safe_prefix = "stock-screener"
    filename = f"{safe_prefix}-{timestamp}.{suffix}"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sanitize_excel_text(value: str) -> str:
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _scan_item_to_row(item: ScreenerScanResultItem) -> list[Any]:
    return [
        _sanitize_excel_text(item.code),
        _sanitize_excel_text(item.name),
        round(float(item.last_close), 2),
        round(float(item.heat), 2) if item.heat is not None else "",
        _sanitize_excel_text(" | ".join(item.matched_conditions)),
        _sanitize_excel_text(" / ".join(item.boards)),
        _sanitize_excel_text(item.data_source),
    ]


def _to_csv_bytes(items: list[ScreenerScanResultItem]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_EXPORT_HEADERS)
    for item in items:
        writer.writerow(_scan_item_to_row(item))
    return output.getvalue().encode("utf-8-sig")


def _to_xlsx_bytes(items: list[ScreenerScanResultItem]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title="选股结果")
    ws.append(_EXPORT_HEADERS)
    for item in items:
        ws.append(_scan_item_to_row(item))
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
