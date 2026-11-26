"""跨模块数据流 API 端点 —— 必须比通用 /{module}/{entry_id} 更早注册。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services.cross_service import (
    mask_rules_for_classify,
    noise_engine_for_budget,
    noise_candidates_for_budget,
    budget_for_differential_query,
    gradient_config_for_secure_agg,
    anomaly_rules_for_audit,
    consent_for_grant,
    k_anonymity_for_pseudonym,
    risk_scan_for_watermark,
    classify_tags_for_deploy,
    gradient_config_for_federated,
    cross_module_summary,
)

router = APIRouter(prefix="/api/cross", tags=["跨模块联动"])


@router.get("/summary")
def cross_summary() -> dict[str, Any]:
    """跨模块数据流汇总快照。"""
    return cross_module_summary()


@router.get("/link/mask_rule+classify_tag/{classify_tag_id}")
def link_mask_rules_classify(classify_tag_id: int) -> dict[str, Any]:
    rules = mask_rules_for_classify(classify_tag_id)
    return {"classify_tag_id": classify_tag_id, "mask_rules": rules, "count": len(rules)}


@router.get("/link/privacy_budget+noise_engine/{privacy_budget_id}")
def link_budget_noise(
    privacy_budget_id: int,
    field: str | None = Query(default=None),
    cost: float | None = Query(default=None),
    all_field_matches: bool = Query(default=False),
) -> dict[str, Any]:
    # noise_configs 保持“关联接口”语义：已生效且字段关联（超费用项仍可被选择提示）。
    # executable_candidates 才是字段相符且费用可承担、可进入执行的候选。
    field_matched = noise_engine_for_budget(privacy_budget_id, field=field, cost=cost)
    executable = noise_engine_for_budget(
        privacy_budget_id, field=field, cost=cost, executable_only=True
    )
    payload: dict[str, Any] = {
        "privacy_budget_id": privacy_budget_id,
        "noise_configs": field_matched,
        "count": len(field_matched),
        "executable_candidates": executable,
    }
    if all_field_matches:
        rich = noise_candidates_for_budget(privacy_budget_id)
        payload["field_matched_configs"] = rich.get("field_matched", [])
        payload["candidate_details"] = rich.get("candidates", [])
    return payload


@router.get("/link/differential_sql+budget/{privacy_budget_id}")
def link_query_budget(privacy_budget_id: int) -> dict[str, Any]:
    info = budget_for_differential_query(privacy_budget_id)
    return {"privacy_budget_id": privacy_budget_id, "budget_info": info}


@router.get("/link/secure_agg+gradient_encrypt/{secure_agg_id}")
def link_agg_gradient(secure_agg_id: int) -> dict[str, Any]:
    configs = gradient_config_for_secure_agg(secure_agg_id)
    return {"secure_agg_id": secure_agg_id, "gradient_configs": configs, "count": len(configs)}


@router.get("/link/access_audit+anomaly_detect/{access_audit_id}")
def link_audit_anomaly(access_audit_id: int) -> dict[str, Any]:
    rules = anomaly_rules_for_audit(access_audit_id)
    return {"access_audit_id": access_audit_id, "anomaly_rules": rules, "count": len(rules)}


@router.get("/link/grant_approval+consent_registry/{grant_approval_id}")
def link_grant_consent(grant_approval_id: int) -> dict[str, Any]:
    consent = consent_for_grant(grant_approval_id)
    return {"grant_approval_id": grant_approval_id, "consent": consent, "has_active": consent is not None}


@router.get("/link/pseudonym+k_anonymity/{pseudonym_id}")
def link_pseudo_k(pseudonym_id: int) -> dict[str, Any]:
    checks = k_anonymity_for_pseudonym(pseudonym_id)
    return {"pseudonym_id": pseudonym_id, "k_checks": checks, "count": len(checks)}


@router.get("/link/watermark+risk_scan/{watermark_id}")
def link_watermark_risk(watermark_id: int) -> dict[str, Any]:
    scans = risk_scan_for_watermark(watermark_id)
    return {"watermark_id": watermark_id, "risk_scans": scans, "count": len(scans)}


@router.get("/link/deploy_policy+classify_tag/{deploy_policy_id}")
def link_deploy_classify(deploy_policy_id: int) -> dict[str, Any]:
    tags = classify_tags_for_deploy(deploy_policy_id)
    return {"deploy_policy_id": deploy_policy_id, "classify_tags": tags, "count": len(tags)}


@router.get("/link/federated_train+gradient_encrypt/{federated_train_id}")
def link_federal_gradient(federated_train_id: int) -> dict[str, Any]:
    configs = gradient_config_for_federated(federated_train_id)
    return {"federated_train_id": federated_train_id, "gradient_configs": configs, "count": len(configs)}