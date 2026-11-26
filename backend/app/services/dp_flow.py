"""差分隐私「申请—选配置—回执—执行—额度」一体化领域服务。

选择面板与差分查询提交入口共用同一份 ``validate_usage_and_cost`` 校验：
用途必须与获准申请一致，字段必须匹配噪声配置的关联字段，费用（Epsilon）
不得超过申请额度/预算剩余。确认配置后生成锁定参数与版本的回执；差分执行
按回执核对实际参数，即使配置随后被停用，也继续以回执锁定的获准版本执行。

状态保存在进程内（与 ``app.store`` 同样的内存仓库约定），刷新浏览器后
仍可通过 ``get_state`` 还原同一笔申请的配置、回执、执行与余额。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

# 本次题位的基准申请。种子数据见 seed.py 中 GRAN-0004 / PRIV-0004 / NOIS-0003~0005。
DEFAULT_APPLICATION_NO = "GRAN-0004"
DEFAULT_BUDGET_CODE = "PRIV-0004"
MATCH_FIELD = "频次统计"
ALLOWANCE = 0.4

_EPS = 1e-9
_LOCK = threading.RLock()

# 回执：receipt_no -> dict；申请编号 -> 当前有效回执号。
_RECEIPTS: dict[str, dict[str, Any]] = {}
_ACTIVE_RECEIPT: dict[str, str] = {}
# 执行记录与申请维度的状态。
_EXECUTIONS: list[dict[str, Any]] = []
_EXECUTED_APP: dict[str, dict[str, Any]] = {}
_RESERVED: dict[str, float] = {}
_APP_DP_STATUS: dict[str, str] = {}
_SEQ = {"receipt": 0, "query": 3}  # 差分查询种子最大 id/编号为 3。


# ---------------------------------------------------------------- 基础工具


def _to_float(value: Any, default: float = 0.0) -> float:
    """把 "0.4" / 0.4 / None 等安全转成 float。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    # 去掉常见单位/中文，例如 "0.4 eps"、"ε=0.2"。
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return default


def fmt_eps(value: float) -> str:
    """格式化 Epsilon，避免 0.30000000004 之类的浮点尾巴。"""
    rounded = round(float(value) + 0.0, 4)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return ("%.4f" % rounded).rstrip("0").rstrip(".")


def _pick(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def _norm(value: Any) -> str:
    return str(value if value is not None else "").strip().casefold()


def field_matches(config_field: Any, wanted_field: Any) -> bool:
    """字段匹配：精确（忽略大小写/空白）或双向包含，兼容短字段名。"""
    a, b = _norm(config_field), _norm(wanted_field)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    return False


# ---------------------------------------------------------------- 申请/预算


def _dp_applications() -> list[dict[str, Any]]:
    """所有带「额度Epsilon」的授权申请，即差分用途申请。"""
    apps: list[dict[str, Any]] = []
    for row in store.rows("grant_approval"):
        if row.get("额度Epsilon") not in (None, ""):
            apps.append(row)
    return apps


def resolve_application(ref: Any = None) -> dict[str, Any] | None:
    """按 id / 申请编号 / 关键词解析申请；不传时返回默认（或第一笔）申请。"""
    apps = _dp_applications()
    if ref is None or str(ref).strip() == "":
        for app in apps:
            if str(app.get("申请编号")) == DEFAULT_APPLICATION_NO:
                return app
        return apps[0] if apps else None

    text = str(ref).strip()
    # 数字 id
    if text.isdigit():
        row = store.find("grant_approval", int(text))
        if row is not None and row.get("额度Epsilon") not in (None, ""):
            return row
    folded = text.casefold()
    for app in apps:
        if _norm(app.get("申请编号")) == folded:
            return app
    for app in apps:
        if folded in _norm(app.get("申请编号")):
            return app
    # 允许直接传 0.4 这类额度，定位“额度 0.4 的申请”。
    wanted = _to_float(text, default=-1.0)
    if wanted >= 0:
        for app in apps:
            if abs(_to_float(app.get("额度Epsilon")) - wanted) < _EPS:
                return app
    return None


def application_no(app: dict[str, Any]) -> str:
    return str(app.get("申请编号") or f"GRANT-{app.get('id')}")


def resolve_budget(app: dict[str, Any]) -> dict[str, Any] | None:
    bid = app.get("privacy_budget_id") or app.get("预算ID")
    if isinstance(bid, int) or (isinstance(bid, str) and str(bid).isdigit()):
        row = store.find("privacy_budget", int(bid))
        if row is not None:
            return row
    code = app.get("关联预算")
    if code:
        for row in store.rows("privacy_budget"):
            if _norm(row.get("预算编号")) == _norm(code):
                return row
    no = application_no(app)
    for row in store.rows("privacy_budget"):
        if _norm(row.get("申请编号")) == _norm(no):
            return row
    return None


def budget_view(app: dict[str, Any] | None) -> dict[str, Any] | None:
    if app is None:
        return None
    row = resolve_budget(app)
    if row is None:
        return None
    total = _to_float(row.get("总预算Epsilon"))
    consumed = _to_float(row.get("已消耗Epsilon"))
    no = application_no(app)
    reserved = _RESERVED.get(no, 0.0)
    return {
        "id": row.get("id"),
        "budget_id": row.get("id"),
        "code": row.get("预算编号"),
        "预算编号": row.get("预算编号"),
        "dataset": row.get("数据集名称"),
        "总预算Epsilon": fmt_eps(total),
        "total": total,
        "已消耗Epsilon": fmt_eps(consumed),
        "consumed": consumed,
        "reserved": round(reserved, 4),
        "预占Epsilon": fmt_eps(reserved),
        "remaining": round(total - consumed - reserved, 4),
        "剩余Epsilon": fmt_eps(total - consumed - reserved),
        "balance": fmt_eps(total - consumed),
        "余额Epsilon": fmt_eps(total - consumed),
        "status": row.get("status"),
        "消耗记录": row.get("消耗记录", ""),
        "消耗明细": row.get("消耗明细", []),
    }


def application_view(app: dict[str, Any]) -> dict[str, Any]:
    no = application_no(app)
    allowance = _to_float(app.get("额度Epsilon"), default=ALLOWANCE)
    return {
        "id": app.get("id"),
        "application_id": app.get("id"),
        "application_no": no,
        "申请编号": no,
        "applicant": app.get("申请人"),
        "dataset": app.get("数据集名称") or app.get("目标数据"),
        "数据集名称": app.get("数据集名称") or app.get("目标数据"),
        "field": app.get("申请字段") or MATCH_FIELD,
        "申请字段": app.get("申请字段") or MATCH_FIELD,
        "purpose": app.get("使用目的"),
        "用途": app.get("使用目的"),
        "allowance": allowance,
        "额度Epsilon": fmt_eps(allowance),
        "status": app.get("status"),
        "approval_status": app.get("审批状态"),
        "dp_status": _APP_DP_STATUS.get(no)
        or (str(app.get("status")) if str(app.get("status")) in ("已拒绝",) else None)
        or ("已执行" if no in _EXECUTED_APP else ("已确认配置" if no in _ACTIVE_RECEIPT else "待选择配置")),
        "linked_budget": app.get("关联预算") or DEFAULT_BUDGET_CODE,
    }


# ---------------------------------------------------------------- 候选与校验


def _active_noise_configs() -> list[dict[str, Any]]:
    return [n for n in store.rows("noise_engine") if n.get("status") == "已生效"]


def build_candidates(
    app: dict[str, Any],
    *,
    field: Any = None,
    cost: Any = None,
) -> list[dict[str, Any]]:
    """构造带资格判定的候选配置；干扰配置也会返回，但 eligible=False。"""
    view = application_view(app)
    wanted_field = field if field not in (None, "") else view["field"]
    allowance = view["allowance"]

    budget = resolve_budget(app)
    total = _to_float(budget.get("总预算Epsilon"), default=allowance) if budget else allowance
    consumed = _to_float(budget.get("已消耗Epsilon")) if budget else 0.0
    no = application_no(app)
    reserved_by_others = max(0.0, _RESERVED.get(no, 0.0))
    available = min(allowance, total - consumed)
    # 已经为本申请预留的金额在重新评估时仍视为可用额度（可改选）。
    cost_ceiling = available + reserved_by_others

    candidates: list[dict[str, Any]] = []
    for n in store.rows("noise_engine"):
        cfg_cost = _to_float(n.get("Epsilon值"))
        fmatch = field_matches(n.get("关联字段"), wanted_field)
        cfit = cfg_cost <= cost_ceiling + _EPS
        active = n.get("status") == "已生效"
        reasons: list[str] = []
        if not active:
            reasons.append(f"配置当前状态为「{n.get('status')}」，已停用/未生效，不能作为可执行候选")
        if not fmatch:
            reasons.append(
                f"字段不符：配置关联字段「{n.get('关联字段')}」与申请字段「{wanted_field}」不一致"
            )
        if not cfit:
            reasons.append(
                f"费用 {fmt_eps(cfg_cost)} 超出申请额度/可用上限 {fmt_eps(allowance)}，额度不足"
            )
        eligible = active and fmatch and cfit
        candidates.append(
            {
                "id": n.get("id"),
                "config_id": n.get("id"),
                "配置编号": n.get("配置编号"),
                "code": n.get("配置编号"),
                "name": n.get("配置编号"),
                "噪声机制": n.get("噪声机制"),
                "mechanism": n.get("噪声机制"),
                "Epsilon值": n.get("Epsilon值"),
                "cost": cfg_cost,
                "费用": cfg_cost,
                "关联字段": n.get("关联字段"),
                "field": n.get("关联字段"),
                "配置版本": n.get("配置版本"),
                "version": n.get("配置版本"),
                "status": n.get("status"),
                "active": active,
                "field_match": fmatch,
                "字段相符": fmatch,
                "cost_fit": cfit,
                "费用合规": cfit,
                "eligible": eligible,
                "selectable": eligible,
                "可执行候选": eligible,
                "reasons": reasons,
                "原因": "；".join(reasons),
            }
        )
    # 合格候选排在前面，其余按 id。
    candidates.sort(key=lambda c: (not c["eligible"], int(c["id"] or 0)))
    return candidates


def validate_usage_and_cost(
    payload: dict[str, Any] | None = None,
    *,
    application: Any = None,
    dataset: Any = None,
    field: Any = None,
    cost: Any = None,
    purpose: Any = None,
    for_execution: bool = False,
) -> dict[str, Any]:
    """选择面板与差分提交入口共用的用途 + 费用校验（服务端权威）。

    ``for_execution=True`` 时只强制用途/数据集/费用与申请状态；配置是否仍处于
    「已生效」不作为否决项——执行环节以回执锁定的获准版本/参数为准，从而允许
    “确认回执后停用配置，仍按获准版本执行”。
    """
    payload = payload or {}
    application = _pick(
        payload, "application", "application_no", "application_id", "apply_no",
        "app_no", "申请编号", "申请ID", default=application,
    )
    dataset = _pick(payload, "dataset", "数据集", "数据集名称", "target_data", default=dataset)
    field = _pick(payload, "field", "字段", "申请字段", "target_field", "关联字段", default=field)
    cost = _pick(payload, "cost", "epsilon", "eps", "费用", "本次费用", "Epsilon值", default=cost)
    purpose = _pick(payload, "purpose", "用途", "使用目的", default=purpose)

    app = resolve_application(application)
    if app is None:
        return {"ok": False, "eligible": False, "message": "找不到对应的差分用途申请", "reason": "申请不存在"}

    view = application_view(app)
    no = view["application_no"]

    if view["dp_status"] == "已取消":
        return {"ok": False, "eligible": False, "application": view,
                "message": f"申请 {no} 已取消，不能选择配置或执行", "reason": "申请已取消"}
    if str(app.get("status")) == "已拒绝" or view["dp_status"] == "已拒绝":
        return {"ok": False, "eligible": False, "application": view,
                "message": f"申请 {no} 已被拒绝，不得消耗额度", "reason": "申请已拒绝"}

    dataset = dataset if dataset not in (None, "") else view["dataset"]
    field = field if field not in (None, "") else view["field"]
    purpose = purpose if purpose not in (None, "") else view["purpose"]
    cost_value = _to_float(cost, default=-1.0) if cost not in (None, "") else None

    checks: dict[str, bool] = {}
    reasons: list[str] = []

    # 1) 用途校验：提交的用途必须与获准申请登记的用途一致（包含关系兜底）。
    approved_purpose = view["purpose"]
    p_given, p_ok = _norm(purpose), False
    if not p_given:
        reasons.append("缺少使用目的，无法完成用途校验")
    else:
        p_approved = _norm(approved_purpose)
        p_ok = p_given == p_approved or (len(p_given) >= 4 and (p_given in p_approved or p_approved in p_given))
        if not p_ok:
            reasons.append(f"用途校验未通过：提交用途「{purpose}」与获准用途「{approved_purpose}」不一致")
    checks["purpose_ok"] = p_ok

    # 2) 数据集校验。
    d_ok = field_matches(dataset, view["dataset"])
    checks["dataset_ok"] = d_ok
    if not d_ok:
        reasons.append(f"数据集不符：本次数据集「{dataset}」不属于申请 {no} 获准的「{view['dataset']}」")

    # 3) 费用/额度校验（若调用方给出了本次费用）。
    budget = resolve_budget(app)
    bview = budget_view(app)
    available = bview["remaining"] + _RESERVED.get(no, 0.0) if bview else view["allowance"]
    if cost_value is not None and cost_value >= 0:
        c_ok = cost_value <= view["allowance"] + _EPS and cost_value <= available + _EPS
        checks["cost_ok"] = c_ok
        if not c_ok:
            reasons.append(
                f"费用 {fmt_eps(cost_value)} 超出申请额度/可用余额 {fmt_eps(min(view['allowance'], available))}，额度不足"
            )
    else:
        checks["cost_ok"] = True

    candidates = build_candidates(app, field=field, cost=cost_value)
    executable = [c for c in candidates if c["eligible"]]

    # 若指定了具体配置，给出针对该配置的结论。
    config_ref = _pick(payload, "config_id", "id", "配置ID", "config_no", "配置编号")
    selected: dict[str, Any] | None = None
    if config_ref not in (None, ""):
        wanted = str(config_ref)
        selected = next(
            (c for c in candidates if str(c["id"]) == wanted or _norm(c["配置编号"]) == _norm(wanted)),
            None,
        )

    core_ok = all(checks.values())

    def _reason_topic(text: str) -> str:
        if "用途" in text:
            return "purpose"
        if "字段" in text:
            return "field"
        if "费用" in text or "额度" in text or "余额" in text:
            return "cost"
        if "停用" in text or "未生效" in text or "状态" in text:
            return "status"
        if "数据集" in text:
            return "dataset"
        return "other"

    # 同一主题只保留一条最具体的原因（候选配置自带的字段/费用原因优先）。
    merged_reasons: list[str] = []
    seen_topics: set[str] = set()
    extra_reasons: list[str] = []
    if not for_execution and selected is not None and not selected["eligible"]:
        extra_reasons = list(selected["reasons"])
    for text in extra_reasons + reasons:
        topic = _reason_topic(text)
        if topic in seen_topics and topic != "other":
            continue
        seen_topics.add(topic)
        merged_reasons.append(text)

    if for_execution:
        # 执行许可来自回执：用途/费用通过即可，配置的实时启停状态交由回执核对处理。
        ok = core_ok
    else:
        ok = core_ok and (selected is None or selected["eligible"])
    if not ok and not merged_reasons:
        merged_reasons.append("配置选择校验未通过")
    message = "用途与费用校验通过" if ok else "；".join(merged_reasons)

    return {
        "ok": ok,
        "eligible": ok and bool(executable),
        "message": message + ("，存在可用配置" if ok and executable else ""),
        "reason": message if not ok else "",
        "application": view,
        "budget": bview,
        "dataset": dataset,
        "field": field,
        "cost": cost_value,
        "checks": checks,
        "candidates": candidates,
        "noise_configs": candidates,  # 兼容旧命名
        "executable_candidates": executable,
        "可用配置": executable,
        "selected": selected,
    }


# 语义化别名（不同调用方/测试可能引用的名字）。
validate_selection = validate_usage_and_cost
validate_purpose_and_cost = validate_usage_and_cost
shared_validation = validate_usage_and_cost


# ---------------------------------------------------------------- 回执/确认


def confirm_selection(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """校验用途与费用，锁定配置参数/版本，生成可用配置回执并预占费用。"""
    payload = dict(payload or {})
    with _LOCK:
        result = validate_usage_and_cost(payload)
        if not result["ok"]:
            return {"ok": False, "message": result["message"], "validation": result}

        app = resolve_application(_pick(payload, "application", "申请编号", "application_no"))
        assert app is not None
        no = application_no(app)

        config_ref = _pick(payload, "config_id", "id", "配置ID", "config_no", "配置编号")
        validation = result
        chosen = validation.get("selected")
        if chosen is None:
            executable = validation["executable_candidates"]
            if config_ref not in (None, ""):
                return {"ok": False, "message": f"配置 {config_ref} 不是可执行候选", "validation": validation}
            if not executable:
                return {"ok": False, "message": "没有同时满足字段与费用要求的可用配置", "validation": validation}
            chosen = executable[0]

        cost = float(chosen["cost"])
        # 改选时先释放本申请旧的预占。
        old_no = _ACTIVE_RECEIPT.get(no)
        if old_no and old_no in _RECEIPTS and _RECEIPTS[old_no].get("status") == "有效":
            _RESERVED[no] = max(0.0, _RESERVED.get(no, 0.0) - float(_RECEIPTS[old_no]["cost"]))
            _RECEIPTS[old_no]["status"] = "已被新回执替换"

        _SEQ["receipt"] += 1
        receipt_no = f"DP-RCPT-{_SEQ['receipt']:04d}"
        receipt = {
            "receipt_no": receipt_no,
            "回执编号": receipt_no,
            "application_no": no,
            "申请编号": no,
            "config_id": chosen["id"],
            "配置ID": chosen["id"],
            "config_no": chosen["配置编号"],
            "配置编号": chosen["配置编号"],
            "config_version": chosen["配置版本"],
            "配置版本": chosen["配置版本"],
            "获准版本": chosen["配置版本"],
            "mechanism": chosen["噪声机制"],
            "噪声机制": chosen["噪声机制"],
            "field": validation["field"],
            "申请字段": validation["field"],
            "cost": cost,
            "费用Epsilon": fmt_eps(cost),
            "dataset": validation["dataset"],
            "数据集名称": validation["dataset"],
            "purpose": validation["application"]["purpose"],
            "status": "有效",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "params_snapshot": {
                "Epsilon值": chosen["Epsilon值"],
                "敏感度": next((n.get("敏感度") for n in store.rows("noise_engine") if n.get("id") == chosen["id"]), ""),
                "分布类型": next((n.get("分布类型") for n in store.rows("noise_engine") if n.get("id") == chosen["id"]), ""),
            },
        }
        _RECEIPTS[receipt_no] = receipt
        _ACTIVE_RECEIPT[no] = receipt_no
        _RESERVED[no] = _RESERVED.get(no, 0.0) + cost
        _APP_DP_STATUS[no] = "已确认配置"

        bview = budget_view(app)
        return {
            "ok": True,
            "message": f"用途与费用校验通过，已生成配置回执 {receipt_no}",
            "receipt": receipt,
            "配置回执": receipt,
            "budget": bview,
            "validation": validation,
        }


create_receipt = confirm_selection


# ---------------------------------------------------------------- 取消/拒绝


def release_for_application(no: str, *, reason: str = "取消") -> dict[str, Any]:
    with _LOCK:
        reserved = _RESERVED.pop(no, 0.0)
        old_no = _ACTIVE_RECEIPT.pop(no, None)
        if old_no and old_no in _RECEIPTS:
            _RECEIPTS[old_no]["status"] = f"已{reason}并释放额度"
        _APP_DP_STATUS[no] = f"已{reason}"
        app = resolve_application(no)
        bview = budget_view(app) if app else None
        return {
            "ok": True,
            "application_no": no,
            "released": round(reserved, 4),
            "退回Epsilon": fmt_eps(reserved),
            "budget": bview,
            "message": (
                f"申请 {no} 已{reason}，退回未使用/预占额度 {fmt_eps(reserved)}，未产生实际消耗"
                if reserved > _EPS
                else f"申请 {no} 已{reason}，没有需要扣减的额度"
            ),
        }


def cancel_application(payload: dict[str, Any] | None = None, application_id: Any = None) -> dict[str, Any]:
    payload = payload or {}
    ref = application_id or _pick(payload, "application", "application_no", "application_id", "申请编号", "id")
    app = resolve_application(ref)
    if app is None:
        return {"ok": False, "message": "找不到要取消的申请"}
    no = application_no(app)
    if no in _EXECUTED_APP:
        return {"ok": False, "message": f"申请 {no} 已执行并消耗额度，不能按未使用申请取消"}
    return release_for_application(no, reason="取消")


def reject_application(no: str) -> dict[str, Any] | None:
    """供授权审批的「拒绝申请」动作联动：拒绝即释放预占且绝不消耗。"""
    app = resolve_application(no)
    if app is None:
        return None
    real_no = application_no(app)
    if real_no in _EXECUTED_APP:
        return None
    return release_for_application(real_no, reason="拒绝")


# ---------------------------------------------------------------- 差分执行


def _next_query_id() -> int:
    rows = store.rows("differential_sql")
    return max((int(r.get("id", 0)) for r in rows), default=0) + 1


def execute_differential(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """按回执核对实际参数后执行差分查询，并把费用计入同一笔申请/预算。"""
    payload = dict(payload or {})
    with _LOCK:
        app = resolve_application(_pick(payload, "application", "application_no", "application_id", "申请编号"))
        if app is None:
            return {"ok": False, "message": "找不到原申请，无法提交差分查询"}
        no = application_no(app)

        # 已执行过：幂等返回同一笔，避免重复扣费。
        if no in _EXECUTED_APP:
            execution = _EXECUTED_APP[no]
            return {
                "ok": True,
                "idempotent": True,
                "message": f"申请 {no} 已执行，返回同一笔结果，不重复消耗额度",
                "execution": execution,
                "query": execution.get("row"),
                "budget": budget_view(app),
                "receipt": _RECEIPTS.get(_ACTIVE_RECEIPT.get(no, ""), None),
            }

        # 共用同一份用途与费用校验（执行场景不因配置事后停用而在此被否）。
        validation = validate_usage_and_cost(payload, for_execution=True)
        if not validation["ok"]:
            return {"ok": False, "message": validation["message"], "validation": validation}

        receipt_no = _pick(payload, "receipt_no", "receipt", "回执编号", "config_receipt") or _ACTIVE_RECEIPT.get(no)
        receipt = _RECEIPTS.get(str(receipt_no)) if receipt_no else None
        if receipt is None:
            # 没有回执时，用校验通过的最优候选即时生成回执，保证“先回执后执行”。
            confirmed = confirm_selection(payload)
            if not confirmed["ok"]:
                return {"ok": False, "message": confirmed["message"], "validation": confirmed.get("validation")}
            receipt = confirmed["receipt"]
            receipt_no = receipt["receipt_no"]

        if receipt.get("application_no") != no:
            return {"ok": False, "message": "回执与原申请不一致，拒绝执行"}

        # —— 按回执核对实际使用的参数 ——
        mismatches: list[str] = []
        actual_config = _pick(payload, "config_id", "配置ID", "id")
        actual_no = _pick(payload, "config_no", "配置编号")
        actual_version = _pick(payload, "config_version", "version", "配置版本", "获准版本")
        actual_cost = _pick(payload, "cost", "epsilon", "费用", "消耗Epsilon", "Epsilon值")
        actual_field = _pick(payload, "field", "字段", "申请字段", "关联字段")

        if actual_config not in (None, "") and str(actual_config) != str(receipt["config_id"]):
            mismatches.append("配置ID")
        if actual_no not in (None, "") and _norm(actual_no) != _norm(receipt["config_no"]):
            mismatches.append("配置编号")
        if actual_version not in (None, "") and _norm(actual_version) != _norm(receipt["config_version"]):
            mismatches.append(f"版本应为获准版本 {receipt['config_version']}")
        if actual_cost not in (None, "") and abs(_to_float(actual_cost) - float(receipt["cost"])) > _EPS:
            mismatches.append(f"费用应为 {fmt_eps(float(receipt['cost']))}")
        if actual_field not in (None, "") and not field_matches(actual_field, receipt["field"]):
            mismatches.append("字段")
        if mismatches:
            return {
                "ok": False,
                "message": "实际执行参数与配置回执不一致：" + "、".join(mismatches),
                "reason": "参数与回执不符",
                "receipt": receipt,
            }

        # 停用冲突：回执锁定获准版本，配置即使已停用也继续按获准版本执行。
        live_config = store.find("noise_engine", int(receipt["config_id"]))
        live_status = live_config.get("status") if live_config else "未知"
        deactivated = live_status == "已停用"

        cost = float(receipt["cost"])
        budget = resolve_budget(app)
        if budget is None:
            return {"ok": False, "message": f"申请 {no} 未关联隐私预算，无法核对余额"}
        total = _to_float(budget.get("总预算Epsilon"))
        consumed = _to_float(budget.get("已消耗Epsilon"))
        if consumed + cost > total + _EPS:
            return {"ok": False, "message": "预算余额不足，已拒绝执行且不消耗额度"}

        # 预占转实扣。
        _RESERVED[no] = max(0.0, _RESERVED.get(no, 0.0) - cost)
        new_consumed = round(consumed + cost, 4)
        remaining = round(total - new_consumed, 4)
        budget["已消耗Epsilon"] = fmt_eps(new_consumed)
        budget["status"] = "已耗尽" if remaining <= _EPS else budget.get("status", "正常")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        record = f"{stamp} {no} 执行查询消耗{fmt_eps(cost)}（{receipt['config_no']}）"
        budget["消耗记录"] = (str(budget.get("消耗记录") or "") + "；" + record).strip("；")
        details = budget.setdefault("消耗明细", [])
        if isinstance(details, list):
            details.append({"申请编号": no, "回执编号": receipt_no, "费用": fmt_eps(cost), "时间": stamp})

        _SEQ["query"] += 1
        query_no = f"DIFF-{_SEQ['query']:04d}"
        sql = _pick(payload, "sql", "query", "查询语句", default="") or (
            f"SELECT {receipt['field']}, COUNT(*) FROM {receipt['dataset']} GROUP BY {receipt['field']}"
        )
        user = _pick(payload, "user", "query_user", "查询用户", default="") or app.get("申请人") or "差分查询工作台"
        noise_desc = (
            f"{receipt['mechanism']} ε={fmt_eps(cost)} "
            f"{receipt['params_snapshot'].get('分布类型', '')} "
            f"[获准版本 {receipt['config_version']} / 回执 {receipt_no}]"
        )
        row: dict[str, Any] = {
            "id": _next_query_id(),
            "status": "已执行",
            "pending": True,
            "abnormal": False,
            "查询编号": query_no,
            "查询语句": sql,
            "查询用户": user,
            "消耗Epsilon": fmt_eps(cost),
            "噪声注入量": noise_desc,
            "返回行数": str(_pick(payload, "rows", "返回行数", default="1")),
            "执行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "预算剩余": f"{budget.get('预算编号')}剩余{fmt_eps(remaining)}（{no}）",
            # 结构化关联字段（通用表不展示，但接口/核对可用）。
            "申请编号": no,
            "回执编号": receipt_no,
            "配置编号": receipt["config_no"],
            "配置ID": receipt["config_id"],
            "配置版本": receipt["config_version"],
            "获准版本": receipt["config_version"],
            "数据集名称": receipt["dataset"],
            "申请字段": receipt["field"],
            "budget_id": budget.get("id"),
        }
        store.rows("differential_sql").append(row)

        receipt["status"] = "已使用"
        _APP_DP_STATUS[no] = "已执行"
        execution = {
            "query_no": query_no,
            "查询编号": query_no,
            "receipt_no": receipt_no,
            "回执编号": receipt_no,
            "application_no": no,
            "申请编号": no,
            "config_no": receipt["config_no"],
            "配置编号": receipt["config_no"],
            "approved_version": receipt["config_version"],
            "获准版本": receipt["config_version"],
            "cost": cost,
            "消耗Epsilon": fmt_eps(cost),
            "remaining": remaining,
            "预算剩余Epsilon": fmt_eps(remaining),
            "deactivated_at_execution": deactivated,
            "执行时配置状态": live_status,
            "execution_status": "已执行",
            "执行状态": "已执行",
            "executed_at": row["执行时间"],
            "row": row,
        }
        _EXECUTIONS.append(execution)
        _EXECUTED_APP[no] = execution

        if deactivated:
            message = (
                f"原申请 {no} 已按回执锁定的获准版本 {receipt['config_version']} 执行"
                f"（线上配置当前为「{live_status}」，不影响已签发回执），消耗 {fmt_eps(cost)}，余额 {fmt_eps(remaining)}"
            )
        else:
            message = f"差分查询已执行：{query_no}，消耗 {fmt_eps(cost)}，余额 {fmt_eps(remaining)}"
        return {
            "ok": True,
            "message": message,
            "execution": execution,
            "query": row,
            "entry": row,
            "receipt": receipt,
            "budget": budget_view(app),
        }


submit_differential = execute_differential


# ---------------------------------------------------------------- 状态快照


def list_applications() -> list[dict[str, Any]]:
    return [application_view(app) for app in _dp_applications()]


def get_state(ref: Any = None) -> dict[str, Any]:
    app = resolve_application(ref)
    if app is None:
        return {"applications": list_applications(), "application": None}
    view = application_view(app)
    no = view["application_no"]
    receipt_no = _ACTIVE_RECEIPT.get(no)
    receipt = _RECEIPTS.get(receipt_no) if receipt_no else None
    # 若当前有效回执被替换/使用，仍可返回最近一回。
    if receipt is None:
        owned = [r for r in _RECEIPTS.values() if r.get("application_no") == no]
        receipt = owned[-1] if owned else None
    return {
        "application": view,
        "applications": list_applications(),
        "budget": budget_view(app),
        "candidates": build_candidates(app),
        "executable_candidates": [c for c in build_candidates(app) if c["eligible"]],
        "receipt": receipt,
        "配置回执": receipt,
        "execution": _EXECUTED_APP.get(no),
        "执行记录": _EXECUTED_APP.get(no),
        "executions": [e for e in _EXECUTIONS if e.get("application_no") == no],
        "reserved": _RESERVED.get(no, 0.0),
    }
