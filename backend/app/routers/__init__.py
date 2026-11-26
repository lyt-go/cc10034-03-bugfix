"""业务路由汇总：差分流程与跨模块链接路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import cross_links, dp_flow, resource

ROUTERS = [dp_flow, cross_links, resource]
