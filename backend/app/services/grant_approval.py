"""授权审批领域服务：拒绝差分用途申请时联动释放预占额度，拒绝即不消耗。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService


class GrantApprovalService(BaseModuleService):
    MODULE = "grant_approval"
    ENTITY = "授权申请"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["申请编号", "申请人", "目标数据", "使用目的", "有效期起", "有效期止", "访问级别", "审批状态"]
    REQUIRED_FIELDS = ["申请编号", "申请人", "目标数据"]
    STATUS_ORDER = ["待审批", "已批准", "已拒绝", "已过期"]
    ACTION_RULES = {"批准申请": "已批准", "拒绝申请": "已拒绝", "标记过期": "已过期"}
    NEGATIVE_ACTIONS = ["拒绝申请"]

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry, message = super().run_action(entry_id, action)
        if entry is not None and action == "拒绝申请":
            # 联动差分流程：拒绝的申请释放配置回执预占，且绝不增加已消耗。
            try:
                from app.services.dp_flow import reject_application

                result = reject_application(str(entry.get("申请编号") or entry_id))
                if result and result.get("message"):
                    message = f"{message}；{result['message']}"
            except Exception:  # 联动失败不影响授权状态流转本身
                pass
        return entry, message
