"""跨模块数据流服务：提供业务Service之间的关联查询和联动操作。

不改变各Service已有的CRUD/状态流转能力，仅在需要跨模块消费时通过本模块完成。
"""
from __future__ import annotations

from typing import Any

from app.store import store


def find_rows(module: str, *, status: str | None = None) -> list[dict[str, Any]]:
    """读取指定模块的全部行，可按状态筛选。"""
    rows = store.rows(module)
    if status:
        return [r for r in rows if r.get("status") == status]
    return list(rows)


def find_by_field(module: str, field: str, value: str) -> list[dict[str, Any]]:
    """按字段值匹配模块行，用于跨模块关联。"""
    rows = store.rows(module)
    return [r for r in rows if str(r.get(field, "")).casefold() == value.casefold()]


# ——————————— 跨模块联动方法 ———————————


def mask_rules_for_classify(classify_tag_id: int) -> list[dict[str, Any]]:
    """给定一个分级标签，返回适用于该标签的生效脱敏规则。"""
    row = store.find("classify_tag", classify_tag_id)
    if not row:
        return []
    requirement = str(row.get("脱敏要求", "")).casefold()
    rules = store.rows("mask_rule")
    results: list[dict[str, Any]] = []
    for r in rules:
        if r.get("status") == "已生效":
            results.append(r)
    return results


def noise_engine_for_budget(
    privacy_budget_id: int,
    *,
    field: str | None = None,
    cost: float | str | None = None,
    executable_only: bool = False,
) -> list[dict[str, Any]]:
    """给定一个隐私预算/用途申请，返回与其字段关联的已生效噪声配置。

    旧实现会把所有「已生效」配置（含无关字段配置）都带出来。这里默认按申请
    字段做关联匹配（修复“无关字段进入关联结果”）；当显式传入 cost 或
    ``executable_only=True`` 时，再按额度/剩余预算过滤费用，得到可执行候选。
    """
    row = store.find("privacy_budget", privacy_budget_id)
    if not row:
        return []

    # 解析申请字段：显式参数 > 预算行自带 > 关联的差分用途申请。
    wanted_field = field or row.get("申请字段")
    app = None
    if not wanted_field:
        try:
            from app.services.dp_flow import resolve_application

            app = resolve_application(row.get("申请编号"))
            if app is not None:
                wanted_field = app.get("申请字段")
        except Exception:
            app = None

    # 费用上限：显式 cost 优先；否则用预算剩余（总额-已消耗）。
    ceiling: float | None
    if cost not in (None, ""):
        try:
            ceiling = float(cost)
        except (TypeError, ValueError):
            ceiling = None
    else:
        try:
            total = float(str(row.get("总预算Epsilon", "0")))
            consumed = float(str(row.get("已消耗Epsilon", "0") or 0))
            ceiling = round(total - consumed, 6)
        except (TypeError, ValueError):
            ceiling = None

    def _cost(n: dict[str, Any]) -> float:
        try:
            return float(str(n.get("Epsilon值", "0")))
        except (TypeError, ValueError):
            return 0.0

    results: list[dict[str, Any]] = []
    for n in store.rows("noise_engine"):
        if n.get("status") != "已生效":
            continue
        if wanted_field:
            from app.services.dp_flow import field_matches

            if not field_matches(n.get("关联字段"), wanted_field):
                continue
        if executable_only and ceiling is not None and _cost(n) > ceiling + 1e-9:
            continue
        results.append(n)
    return results


def noise_candidates_for_budget(privacy_budget_id: int) -> dict[str, Any]:
    """返回区分「字段关联」与「可执行候选」的完整候选结构（含排除原因）。"""
    row = store.find("privacy_budget", privacy_budget_id)
    if not row:
        return {"field_matched": [], "executable": [], "all_active": []}
    field_name = row.get("申请字段")
    try:
        from app.services.dp_flow import resolve_application, validate_usage_and_cost

        app = resolve_application(row.get("申请编号") or privacy_budget_id)
        if app is not None:
            state = validate_usage_and_cost({"application": app.get("申请编号")})
            return {
                "application": state.get("application"),
                "field_matched": [c for c in state.get("candidates", []) if c.get("field_match")],
                "executable": state.get("executable_candidates", []),
                "candidates": state.get("candidates", []),
            }
    except Exception:
        pass
    executable = noise_engine_for_budget(privacy_budget_id)
    field_matched = noise_engine_for_budget(privacy_budget_id, executable_only=False)
    return {"field_matched": field_matched, "executable": executable, "candidates": field_matched}


def budget_for_differential_query(privacy_budget_id: int) -> dict[str, Any] | None:
    """给定差分查询关联的预算ID，返回剩余预算信息。"""
    row = store.find("privacy_budget", privacy_budget_id)
    if not row:
        return None
    return {
        "budget_id": row.get("id"),
        "total": row.get("总预算Epsilon"),
        "consumed": row.get("已消耗Epsilon"),
        "status": row.get("status"),
        "reset_time": row.get("重置时间"),
    }


def gradient_config_for_secure_agg(secure_agg_id: int) -> list[dict[str, Any]]:
    """给定安全聚合任务，返回已启用的梯度加密配置。"""
    row = store.find("secure_agg", secure_agg_id)
    if not row:
        return []
    configs = store.rows("gradient_encrypt")
    results: list[dict[str, Any]] = []
    for c in configs:
        if c.get("status") in ("已启用", "待验证"):
            results.append(c)
    return results


def anomaly_rules_for_audit(access_audit_id: int) -> list[dict[str, Any]]:
    """给定访问审计记录，返回匹配的异常检测规则。"""
    row = store.find("access_audit", access_audit_id)
    if not row:
        return []
    level = str(row.get("敏感等级", "")).casefold()
    rules = store.rows("anomaly_detect")
    results: list[dict[str, Any]] = []
    for r in rules:
        if r.get("status") in ("已启用", "待验证"):
            results.append(r)
    return results


def consent_for_grant(grant_approval_id: int) -> dict[str, Any] | None:
    """给定授权申请，检查关联的数据主体是否已有有效同意记录。"""
    row = store.find("grant_approval", grant_approval_id)
    if not row:
        return None
    applicant = str(row.get("申请人", ""))
    consents = store.rows("consent_registry")
    for c in consents:
        if str(c.get("数据主体", "")).casefold().find(applicant.casefold()) >= 0 and c.get("status") == "已同意":
            return c
    return None


def k_anonymity_for_pseudonym(pseudonym_id: int) -> list[dict[str, Any]]:
    """给定假名映射，返回相关的K匿名检查结果。"""
    row = store.find("pseudonym", pseudonym_id)
    if not row:
        return []
    checks = store.rows("k_anonymity")
    results: list[dict[str, Any]] = []
    for c in checks:
        if c.get("status") in ("已通过", "未通过"):
            results.append(c)
    return results


def risk_scan_for_watermark(watermark_id: int) -> list[dict[str, Any]]:
    """给定水印记录，返回关联的风险扫描结果。"""
    row = store.find("watermark", watermark_id)
    if not row:
        return []
    scans = store.rows("risk_scan")
    results: list[dict[str, Any]] = []
    for s in scans:
        if s.get("status") in ("已完成", "扫描中"):
            results.append(s)
    return results


def classify_tags_for_deploy(deploy_policy_id: int) -> list[dict[str, Any]]:
    """给定策略分发记录，返回适用的分级标签。"""
    row = store.find("deploy_policy", deploy_policy_id)
    if not row:
        return []
    tags = store.rows("classify_tag")
    results: list[dict[str, Any]] = []
    for t in tags:
        if t.get("status") in ("已分级", "需重审"):
            results.append(t)
    return results


def gradient_config_for_federated(federated_train_id: int) -> list[dict[str, Any]]:
    """给定联邦训练任务，返回关联的梯度加密配置。"""
    row = store.find("federated_train", federated_train_id)
    if not row:
        return []
    configs = store.rows("gradient_encrypt")
    results: list[dict[str, Any]] = []
    for c in configs:
        if c.get("status") in ("已启用", "待验证"):
            results.append(c)
    return results


# ——————————— 汇总快照 ———————————


def cross_module_summary() -> dict[str, Any]:
    """生成跨模块关联快照，用于容量展示。"""
    pairs = [
        ("mask_rule+classify_tag", len(mask_rules_for_classify(2))),
        ("privacy_budget+noise_engine", len(noise_engine_for_budget(1))),
        ("differential_sql+budget", bool(budget_for_differential_query(1))),
        ("secure_agg+gradient_encrypt", len(gradient_config_for_secure_agg(1))),
        ("access_audit+anomaly_detect", len(anomaly_rules_for_audit(2))),
        ("grant_approval+consent_registry", bool(consent_for_grant(2))),
        ("pseudonym+k_anonymity", len(k_anonymity_for_pseudonym(1))),
        ("watermark+risk_scan", len(risk_scan_for_watermark(2))),
        ("deploy_policy+classify_tag", len(classify_tags_for_deploy(2))),
        ("federated_train+gradient_encrypt", len(gradient_config_for_federated(2))),
    ]
    total = sum(1 for _, count in pairs if count)
    return {"pairs": [{"key": k, "linked": v} for k, v in pairs], "linked_count": total}