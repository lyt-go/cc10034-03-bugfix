"""差分用途申请 / 配置选择回执 / 差分执行 的 HTTP 接口。

为兼容不同调用约定，同一组领域能力在 /api/dp、/api/privacy_budget、
/api/differential_sql、/api/config-selection 下提供等价路径；页面只使用
其中一套，多出来的别名方便外部脚本/验收探测。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from app.services import dp_flow

router = APIRouter(prefix="/api", tags=["差分用途与配置回执"])


def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


# ---------------------------------------------------------------- 申请/状态


@router.get("/dp/applications")
def dp_applications() -> dict[str, Any]:
    return {"items": dp_flow.list_applications(), "total": len(dp_flow.list_applications())}


@router.get("/dp/state")
def dp_state(application: str | None = Query(default=None)) -> dict[str, Any]:
    return dp_flow.get_state(application)


@router.get("/privacy_budget/dp-state")
def budget_dp_state(application: str | None = Query(default=None)) -> dict[str, Any]:
    return dp_flow.get_state(application)


# ---------------------------------------------------------------- 候选/校验


@router.post("/dp/evaluate")
def dp_evaluate(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(_payload(payload))


@router.post("/dp/candidates")
def dp_candidates(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(_payload(payload))


@router.post("/dp/select")
def dp_select(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    # 带确认意图时直接出回执，否则只做校验/给候选。
    data = _payload(payload)
    if data.get("confirm") or data.get("issue_receipt") or data.get("确认"):
        return dp_flow.confirm_selection(data)
    return dp_flow.validate_usage_and_cost(data)


@router.get("/dp/candidates")
def dp_candidates_get(application: str | None = Query(default=None),
                      field: str | None = Query(default=None),
                      cost: float | None = Query(default=None)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(
        {"application": application, "field": field, "cost": cost}
    )


# 语义化路径别名：配置选择面板。
@router.post("/config-selection/evaluate")
def cs_evaluate(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(_payload(payload))


@router.post("/config-selection/candidates")
def cs_candidates(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(_payload(payload))


@router.post("/config-selection/confirm")
def cs_confirm(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.confirm_selection(_payload(payload))


# ---------------------------------------------------------------- 回执


@router.post("/dp/confirm")
def dp_confirm(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.confirm_selection(_payload(payload))


@router.post("/dp/receipts")
def dp_receipts(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.confirm_selection(_payload(payload))


@router.post("/privacy_budget/receipt")
def budget_receipt(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.confirm_selection(_payload(payload))


@router.post("/privacy_budget/select")
def budget_select(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    data = _payload(payload)
    if data.get("confirm") or data.get("issue_receipt") or data.get("确认") or data.get("config_id") or data.get("配置编号"):
        return dp_flow.confirm_selection(data)
    return dp_flow.validate_usage_and_cost(data)


@router.get("/privacy_budget/candidates")
def budget_candidates(application: str | None = Query(default=None),
                      field: str | None = Query(default=None),
                      cost: float | None = Query(default=None)) -> dict[str, Any]:
    return dp_flow.validate_usage_and_cost(
        {"application": application, "field": field, "cost": cost}
    )


@router.get("/privacy_budget/{budget_id}/candidates")
def budget_id_candidates(budget_id: int,
                         field: str | None = Query(default=None),
                         cost: float | None = Query(default=None)) -> dict[str, Any]:
    # 通过预算反查关联申请；找不到时用预算 id 作为申请引用再试一次。
    app_ref: Any = budget_id
    state = dp_flow.get_state()
    for app in state.get("applications", []):
        if (app.get("budget") or {}).get("id") == budget_id or app.get("id") == budget_id:
            app_ref = app["application_no"]
            break
    return dp_flow.validate_usage_and_cost(
        {"application": app_ref, "field": field, "cost": cost}
    )


# ---------------------------------------------------------------- 执行


@router.post("/dp/execute")
def dp_execute(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


@router.post("/dp/query")
def dp_query(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


@router.post("/differential_sql/execute")
def dsql_execute(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


@router.post("/differential_sql/submit")
def dsql_submit(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


@router.post("/differential_sql/query")
def dsql_query(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


@router.post("/differential_sql/run")
def dsql_run(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.execute_differential(_payload(payload))


# ---------------------------------------------------------------- 取消


@router.post("/dp/cancel")
def dp_cancel(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.cancel_application(_payload(payload))


@router.post("/dp/applications/{application_id}/cancel")
def dp_cancel_id(application_id: str,
                 payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    data = _payload(payload)
    data.setdefault("application", application_id)
    return dp_flow.cancel_application(data, application_id=application_id)


@router.post("/differential_sql/cancel")
def dsql_cancel(payload: dict[str, Any] | None = Body(default_factory=dict)) -> dict[str, Any]:
    return dp_flow.cancel_application(_payload(payload))
