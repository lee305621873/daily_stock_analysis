# -*- coding: utf-8 -*-
"""
===================================
API v1 模块初始化
===================================

职责：
1. 懒加载导出 v1 版本 API 的路由
2. 避免导入 schema/service 时触发 router -> endpoint 的循环导入
"""

__all__ = ["api_v1_router"]


def __getattr__(name: str):
    if name == "api_v1_router":
        from api.v1.router import router as api_v1_router

        return api_v1_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
