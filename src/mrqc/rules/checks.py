"""七类 check_type 确定性检查函数（M3）。

分派约定：引擎按 rule.type 分派到本模块 handler，handler 签名统一为
``handler(rule, card, part_texts) -> List[Finding]``，一条规则产出一个结论
（pass / fail / need_confirm），便于报告逐规则展示与评测对账。

判定纪律（plan/04 §3 / plan/06）：
- 数据不足以判定（事件/字段/部件缺失）→ 一律 pass，不硬判、不误报；
- 依据 status=待核对（或 severity=NEED_CONFIRM）→ 结论只能 need_confirm；
- 多解情形（如术后诊断与出院诊断不一致可能属合法补充诊断）→ need_confirm；
- 结论证据一律用参数卡 Evidence 或部件原文行（逐字子串，防幻觉纪律）。

required_field 数据源定稿（plan/06）：区块存在性由解析层判定（parse_warnings
"X缺少区块：Y"，M2 告警口径锁定），规则层只消费其结论，不重查部件文本。
"""

from datetime import timedelta
from typing import Dict, List, Optional

from ..models import Evidence, RecordCard
from .finding import Basis, Finding, Severity

__all__ = ["RULE_DISPATCH"]

_DT = "%Y-%m-%d %H:%M"
BLOOD_PURPOSE = "术中用血"  # 与 render._card_med / knowledge.drugs 口径一致


# ---------------------------------------------------------------- 公共小件

def _parse_dt(s: str):
    from datetime import datetime
    try:
        return datetime.strptime(s.strip(), _DT)
    except (ValueError, AttributeError):
        return None


def _val(fv):
    return fv.value if fv is not None else None


def _quote(fv) -> Optional[Evidence]:
    if fv is not None and fv.evidence:
        return fv.evidence[0]
    return None


def _timeline(card: RecordCard, event: str) -> list:
    return [e for e in card.timeline if e.event == event]


def _first_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def _fill(template: str, ctx: Dict[str, str]) -> str:
    out = template
    for key, val in ctx.items():
        out = out.replace("{%s}" % key, val)
    return out


def _finding(rule, status: str, evidence: List[Evidence], ctx: Dict[str, str]) -> Finding:
    severity = rule.severity
    if status != "pass" and (rule.basis.status != "已核对" or severity is Severity.NEED_CONFIRM):
        # 纪律：待核对依据 / 待确认级别只能产出 need_confirm 结论
        status = "need_confirm"
        severity = Severity.NEED_CONFIRM
    return Finding(
        rule_id=rule.id, rule_name=rule.name, severity=severity, basis=rule.basis,
        evidence=evidence, suggestion=_fill(rule.suggestion_template, ctx), status=status,
    )


def _verdict(rule, violated: bool, evidence: List[Evidence],
             fail_ctx: Optional[Dict[str, str]] = None,
             need_confirm: bool = False):
    """统一裁决：未违例 → pass；违例 → fail（待核对依据 → need_confirm）。"""
    if not violated:
        finding = _finding(rule, "pass", [e for e in evidence if e], {})
        finding.suggestion = ""  # 通过结论无整改建议
        return finding
    ctx = fail_ctx or {}
    status = "need_confirm" if need_confirm else "fail"
    return _finding(rule, status, [e for e in evidence if e], ctx)


def _hours(delta: timedelta) -> str:
    return "%.1f" % (delta.total_seconds() / 3600.0)


def _dedupe(evidence: List[Evidence]) -> List[Evidence]:
    seen, out = set(), []
    for e in evidence:
        if e is None:
            continue
        key = (e.part, e.quote)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


# ---------------------------------------------------------------- required_field

def check_required_field(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    """必填项存在性。数据源：parse_warnings（解析层区块存在性结论）。

    部件整体缺失不在此判（部件可缺是既定口径，如 CAP 无手术记录）；
    R-REQ-06（手术病种缺手术记录）以"出院记录提及手术但无手术记录部件"为触发。
    """
    p = rule.params
    if p.get("require") == "surgery_record":
        dtext = texts.get("出院记录", "")
        mentions = "手术" in dtext
        has_record = bool(card.surgeries) or "手术记录" in texts
        if mentions and not has_record:
            ev = Evidence(part="出院记录", quote=_first_line(dtext)) if dtext else None
            return [_verdict(rule, True, [ev])]
        return [_verdict(rule, False, [])]
    part = p.get("part", "")
    blocks = p.get("blocks") or ([p["block"]] if p.get("block") else [])
    if part not in texts or not blocks:
        return [_verdict(rule, False, [])]
    missing = [b for b in blocks
               if "%s缺少区块：%s" % (part, b) in card.parse_warnings]
    if missing:
        ev = Evidence(part=part, quote=_first_line(texts[part]))
        return [_verdict(rule, True, [ev], {"missing": "、".join(missing)})]
    return [_verdict(rule, False, [])]


# ---------------------------------------------------------------- timeliness

def _anchor_time(rule, card: RecordCard):
    """返回（锚点 datetime, 锚点证据）；无法判定返回 (None, None)。"""
    p = rule.params
    if p.get("anchor") == "surgery_end":
        if not card.surgeries:
            return None, None
        s = card.surgeries[0]
        start = _parse_dt(_val(s.start_time) or "")
        duration = _val(s.duration_min)
        if start is None or duration is None:
            return None, None
        return start + timedelta(minutes=int(duration)), _quote(s.start_time)
    anchor_events = _timeline(card, p.get("anchor_event", ""))
    if not anchor_events or anchor_events[0].time is None:
        return None, None
    return _parse_dt(anchor_events[0].time.value or ""), _quote(anchor_events[0].time)


def check_timeliness(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    """书写时限：事件完成时间相对锚点（入院/手术结束）不得超过 limit_hours。

    事件缺失不判（完整性归 required_field 通道）；时限值为负（先于锚点）
    属时间轴矛盾，归 timeline_logic 通道，此处不判。
    """
    p = rule.params
    events = _timeline(card, p.get("event", ""))
    if not events or events[0].time is None:
        return [_verdict(rule, False, [])]
    anchor_dt, anchor_ev = _anchor_time(rule, card)
    done_dt = _parse_dt(events[0].time.value or "")
    if anchor_dt is None or done_dt is None:
        return [_verdict(rule, False, [])]
    delta = done_dt - anchor_dt
    limit_min = float(p.get("limit_hours", 0)) * 60.0
    violated = delta.total_seconds() > limit_min * 60.0
    evidence = [anchor_ev, _quote(events[0].time)]
    return [_verdict(rule, violated, evidence, {"actual_hours": _hours(delta)})]


# ---------------------------------------------------------------- cross_consistency

def _compare_diagnosis_medication(rule, card, texts):
    kws = rule.params.get("diagnosis_keywords", [])
    dx = [d for d in card.diagnoses if d.type == "出院" and _val(d.name)]
    hit = [d for d in dx if any(k in _val(d.name) for k in kws)]
    if not hit:
        return _verdict(rule, False, [])
    has_ab = any(_val(m.is_antibiotic) for m in card.medications)
    evidence = [_quote(hit[0].name)]
    if card.medications:
        evidence.append(_quote(card.medications[0].drug_name))
    return _verdict(rule, not has_ab, evidence, {"diag": _val(hit[0].name)})


def _compare_surgery_name_vs_preop(rule, card, texts):
    disc = _timeline(card, "术前讨论")
    if not disc or not card.surgeries:
        return _verdict(rule, False, [])
    performed = _val(card.surgeries[0].name)
    planned = disc[0].detail
    if not performed or not planned:
        return _verdict(rule, False, [])
    evidence = [_quote(card.surgeries[0].name)]
    # 术前讨论原文行（含拟施术式）作证据；取不到退回事件时间证据
    course = texts.get("病程记录", "")
    line_ev = None
    for ln in course.splitlines():
        if "拟施手术：%s" % planned in ln:
            line_ev = Evidence(part="病程记录", quote=ln.strip())
            break
    evidence.append(line_ev or _quote(disc[0].time))
    return _verdict(rule, performed != planned, evidence,
                    {"performed": performed, "planned": planned})


def _compare_surgeon_vs_signature(rule, card, texts):
    """术者签名缺失时按约定跳过（缺失由 F-SIGN-01 负责，plan/06 注入跳过约定）。"""
    sig = [s for s in card.signatures if s.role == "术者"]
    if not sig or not card.surgeries:
        return _verdict(rule, False, [])
    surgeon = _val(card.surgeries[0].surgeon)
    signed = _val(sig[0].name)
    if not surgeon or not signed:
        return _verdict(rule, False, [])
    evidence = [_quote(card.surgeries[0].surgeon), _quote(sig[0].name)]
    return _verdict(rule, surgeon != signed, evidence,
                    {"surgeon": surgeon, "signed": signed})


def _compare_med_stop_vs_discharge(rule, card, texts):
    discharge = _val(card.patient.discharge_date)
    if not discharge:
        return _verdict(rule, False, [])
    offenders = [m for m in card.medications
                 if _val(m.stop_time) and _val(m.stop_time) > discharge]
    evidence = [m.stop_time.evidence[0] for m in offenders if m.stop_time.evidence]
    evidence.append(_quote(card.patient.discharge_date))
    ctx = {}
    if offenders:
        ctx = {"drug": _val(offenders[0].drug_name) or "",
               "stop": _val(offenders[0].stop_time), "discharge": discharge}
    return _verdict(rule, bool(offenders), evidence, ctx)


def _compare_admission_date_across_parts(rule, card, texts):
    adm = _val(card.patient.admission_date)
    dtext = texts.get("出院记录", "")
    if not adm or not dtext:
        return _verdict(rule, False, [])
    lines = [ln.strip() for ln in dtext.splitlines() if ln.startswith("入院时间：")]
    if not lines:
        return _verdict(rule, False, [])
    mismatched = [ln for ln in lines if ln[len("入院时间："):].strip() != adm]
    evidence = [_quote(card.patient.admission_date),
                Evidence(part="出院记录", quote=lines[0])]
    return _verdict(rule, bool(mismatched), evidence,
                    {"in_discharge": lines[0][len("入院时间："):].strip(),
                     "in_admission": adm})


def _compare_hospital_days(rule, card, texts):
    adm = _parse_dt(_val(card.patient.admission_date) or "")
    dis = _parse_dt(_val(card.patient.discharge_date) or "")
    days = _val(card.patient.hospital_days)
    if adm is None or dis is None or days is None:
        return _verdict(rule, False, [])
    computed = (dis.date() - adm.date()).days
    evidence = [_quote(card.patient.hospital_days), _quote(card.patient.admission_date),
                _quote(card.patient.discharge_date)]
    return _verdict(rule, days != computed, evidence,
                    {"days": days, "computed": computed})


def _compare_postop_dx_vs_discharge_dx(rule, card, texts):
    post = [d for d in card.diagnoses if d.type == "术后" and _val(d.name)]
    dis = [d for d in card.diagnoses if d.type == "出院" and _val(d.name)]
    if not post or not dis:
        return _verdict(rule, False, [])
    same = _val(post[0].name) == _val(dis[0].name)
    # 多解情形：不一致可能属合法补充诊断 → need_confirm，不硬判
    return _verdict(rule, not same, [_quote(post[0].name), _quote(dis[0].name)],
                    {"postop": _val(post[0].name), "discharge": _val(dis[0].name)},
                    need_confirm=True)


_COMPARES = {
    "diagnosis_medication": _compare_diagnosis_medication,
    "surgery_name_vs_preop": _compare_surgery_name_vs_preop,
    "surgeon_vs_operator_signature": _compare_surgeon_vs_signature,
    "med_stop_vs_discharge": _compare_med_stop_vs_discharge,
    "admission_date_across_parts": _compare_admission_date_across_parts,
    "hospital_days_vs_dates": _compare_hospital_days,
    "postop_dx_vs_discharge_dx": _compare_postop_dx_vs_discharge_dx,
}


def check_cross_consistency(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    handler = _COMPARES.get(rule.params.get("compare", ""))
    if handler is None:
        return [_verdict(rule, False, [])]
    return [handler(rule, card, texts)]


# ---------------------------------------------------------------- medication_logic

def _check_special_antibiotic_approval(rule, card, texts):
    level = rule.params.get("level", "特殊使用级")
    specials = [m for m in card.medications if _val(m.antibiotic_level) == level]
    if not specials:
        return _verdict(rule, False, [])
    course = texts.get("病程记录", "")
    kws = rule.params.get("approval_keywords", [])
    approved = any(k in course for k in kws) or any(
        _val(m.drug_name) and _val(m.drug_name) in course for m in specials)
    evidence = [_quote(m.drug_name) for m in specials]
    return _verdict(rule, not approved, evidence, {"drug": _val(specials[0].drug_name) or ""})


def _check_blood_approval(rule, card, texts):
    """用血医嘱识别走参数卡 purpose（"输血"字样全语料出现于"未输血"，不可作关键词）。"""
    bloods = [m for m in card.medications if _val(m.purpose) == BLOOD_PURPOSE]
    if not bloods:
        return _verdict(rule, False, [])
    has_approval = bool(_timeline(card, "用血审批"))
    evidence = [_quote(m.drug_name) for m in bloods]
    if has_approval:
        ev = _quote(_timeline(card, "用血审批")[0].time)
        evidence.append(ev)
    return _verdict(rule, not has_approval, evidence, {"drug": _val(bloods[0].drug_name) or ""})


def _check_order_completeness(rule, card, texts):
    scope = rule.params.get("scope", "longterm")
    fields = rule.params.get("fields", [])
    if scope == "longterm":
        pool = [m for m in card.medications if m.stop_time is not None]
    else:
        pool = [m for m in card.medications if m.stop_time is None]
    missing = [(m, [f for f in fields if getattr(m, f, None) is None]) for m in pool]
    missing = [(m, absent) for m, absent in missing if absent]
    evidence = [_quote(m.drug_name) for m, _ in missing]
    ctx = {}
    if missing:
        m0, absent0 = missing[0]
        ctx = {"drug": _val(m0.drug_name) or "", "missing": "、".join(absent0)}
    return _verdict(rule, bool(missing), evidence, ctx)


def _check_antibiotic_level(rule, card, texts):
    unmarked = [m for m in card.medications
                if _val(m.is_antibiotic) and not _val(m.antibiotic_level)]
    evidence = [_quote(m.drug_name) for m in unmarked]
    ctx = {"drug": _val(unmarked[0].drug_name) or ""} if unmarked else {}
    return _verdict(rule, bool(unmarked), evidence, ctx)


_MEDICATION_CHECKS = {
    "special_antibiotic_approval": _check_special_antibiotic_approval,
    "blood_approval": _check_blood_approval,
    "order_completeness": _check_order_completeness,
    "antibiotic_level_present": _check_antibiotic_level,
}


def check_medication_logic(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    handler = _MEDICATION_CHECKS.get(rule.params.get("check", ""))
    if handler is None:
        return [_verdict(rule, False, [])]
    return [handler(rule, card, texts)]


# ---------------------------------------------------------------- lab_logic

def _critical_labs(card: RecordCard) -> list:
    return [l for l in card.labs if _val(l.is_critical)]


def _check_critical_closed_loop(rule, card, texts):
    crits = _critical_labs(card)
    if not crits:
        return _verdict(rule, False, [])
    course = texts.get("病程记录", "")
    marker = rule.params.get("handling_marker", "危急值处置")
    handled = marker in course
    evidence = []
    for l in crits:
        if l.is_critical.evidence:
            evidence.append(l.is_critical.evidence[0])
    ctx = {"item": _val(crits[0].item_name) or "",
           "value": _val(crits[0].value) or "", "unit": _val(crits[0].unit) or ""}
    return _verdict(rule, not handled, evidence, ctx)


def _check_critical_item_unaddressed(rule, card, texts):
    item = rule.params.get("item", "")
    hits = [l for l in card.labs
            if _val(l.item_name) == item and _val(l.is_critical)]
    if not hits:
        return _verdict(rule, False, [])
    course = texts.get("病程记录", "")
    mentioned = item in course
    kws = rule.params.get("diagnosis_keywords", [])
    dx_hit = any(k in (_val(d.name) or "")
                 for d in card.diagnoses for k in kws)
    evidence = []
    for l in hits:
        if l.is_critical.evidence:
            evidence.append(l.is_critical.evidence[0])
    ctx = {"item": item, "value": _val(hits[0].value) or "",
           "unit": _val(hits[0].unit) or ""}
    return _verdict(rule, (not mentioned) and (not dx_hit), evidence, ctx)


def _check_report_time(rule, card, texts):
    missing = [l for l in card.labs if l.report_time is None]
    evidence = []
    for l in missing:
        if l.item_name is not None and l.item_name.evidence:
            evidence.append(l.item_name.evidence[0])
    ctx = {"item": _val(missing[0].item_name) or ""} if missing else {}
    return _verdict(rule, bool(missing), evidence, ctx)


_LAB_CHECKS = {
    "critical_closed_loop": _check_critical_closed_loop,
    "critical_item_unaddressed": _check_critical_item_unaddressed,
    "report_time_present": _check_report_time,
}


def check_lab_logic(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    handler = _LAB_CHECKS.get(rule.params.get("check", ""))
    if handler is None:
        return [_verdict(rule, False, [])]
    return [handler(rule, card, texts)]


# ---------------------------------------------------------------- signature_format

def _check_required_signatures(rule, card, texts):
    missing_roles = []
    evidence = []
    for item in rule.params.get("items", []):
        role = item.get("role", "")
        if item.get("when_surgery") and not card.surgeries:
            continue  # 无手术病种不要求术者签名
        require_part = item.get("require_part", "")
        if require_part and require_part not in texts:
            continue  # 部件整体缺失不判（部件可缺是既定口径）
        if not any(s.role == role for s in card.signatures):
            missing_roles.append(role)
            if card.surgeries and role == "术者":
                evidence.append(_quote(card.surgeries[0].surgeon))
            elif role == "主治医师" and _quote(card.patient.discharge_date) is not None:
                evidence.append(_quote(card.patient.discharge_date))
    return _verdict(rule, bool(missing_roles), evidence, {"roles": "、".join(missing_roles)})


def _check_signature_date(rule, card, texts):
    no_date = [s for s in card.signatures if s.date is None]
    evidence = [_quote(s.name) for s in no_date]
    ctx = {"roles": "、".join(s.role for s in no_date)} if no_date else {}
    return _verdict(rule, bool(no_date), evidence, ctx)


def _check_role_present(rule, card, texts):
    role = rule.params.get("role", "")
    require_part = rule.params.get("require_part", "")
    if require_part and require_part not in texts:
        return _verdict(rule, False, [])
    present = any(s.role == role for s in card.signatures)
    evidence = []
    if not present and card.patient.name is not None:
        evidence.append(_quote(card.patient.name))
    return _verdict(rule, not present, evidence, {})


_SIGNATURE_CHECKS = {
    "required_signatures": _check_required_signatures,
    "signature_date_present": _check_signature_date,
    "role_present": _check_role_present,
}


def check_signature_format(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    handler = _SIGNATURE_CHECKS.get(rule.params.get("check", ""))
    if handler is None:
        return [_verdict(rule, False, [])]
    return [handler(rule, card, texts)]


# ---------------------------------------------------------------- timeline_logic

def check_timeline_logic(rule, card: RecordCard, texts: Dict[str, str]) -> List[Finding]:
    check = rule.params.get("check", "")
    adm = _val(card.patient.admission_date)
    dis = _val(card.patient.discharge_date)
    surgery = card.surgeries[0] if card.surgeries else None

    if check == "discharge_after_surgery":
        if surgery is None:
            return [_verdict(rule, False, [])]
        ev = [_quote(card.patient.discharge_date), _quote(surgery.start_time)]
        ctx = {"discharge": dis or "", "surgery": _val(surgery.start_time) or ""}
        violated = bool(dis and _val(surgery.start_time) and dis < _val(surgery.start_time))
        return [_verdict(rule, violated, ev, ctx)]

    if check == "surgery_after_admission":
        if surgery is None:
            return [_verdict(rule, False, [])]
        ev = [_quote(surgery.start_time), _quote(card.patient.admission_date)]
        ctx = {"surgery": _val(surgery.start_time) or "", "admission": adm or ""}
        return [_verdict(rule, bool(_val(surgery.start_time) and adm and _val(surgery.start_time) < adm), ev, ctx)]

    if check == "preop_before_surgery":
        disc = _timeline(card, "术前讨论")
        if not disc or surgery is None:
            return [_verdict(rule, False, [])]
        preop = _val(disc[0].time)
        ev = [_quote(disc[0].time), _quote(surgery.start_time)]
        ctx = {"preop": preop or "", "surgery": _val(surgery.start_time) or ""}
        return [_verdict(rule, bool(preop and _val(surgery.start_time) and preop > _val(surgery.start_time)), ev, ctx)]

    if check == "first_course_after_admission":
        fc = _timeline(card, "首次病程记录")
        if not fc:
            return [_verdict(rule, False, [])]
        ev = [_quote(fc[0].time), _quote(card.patient.admission_date)]
        ctx = {"first_course": _val(fc[0].time) or "", "admission": adm or ""}
        return [_verdict(rule, bool(_val(fc[0].time) and adm and _val(fc[0].time) < adm), ev, ctx)]

    if check == "record_time_after_admission":
        rt = _timeline(card, "入院记录完成")
        if not rt:
            return [_verdict(rule, False, [])]
        ev = [_quote(rt[0].time), _quote(card.patient.admission_date)]
        ctx = {"record_time": _val(rt[0].time) or "", "admission": adm or ""}
        return [_verdict(rule, bool(_val(rt[0].time) and adm and _val(rt[0].time) < adm), ev, ctx)]

    if check == "critical_handling_after_report":
        crits = _critical_labs(card)
        handling = _timeline(card, "危急值处置")
        if not crits or not handling:
            return [_verdict(rule, False, [])]
        reports = [_val(l.report_time) for l in crits if _val(l.report_time)]
        h = _val(handling[0].time)
        if not reports or not h:
            return [_verdict(rule, False, [])]
        violated = any(h < r for r in reports)
        ev = [_quote(handling[0].time)]
        for l in crits:
            if l.is_critical.evidence:
                ev.append(l.is_critical.evidence[0])
        ctx = {"handling": h, "report": min(r for r in reports if h > r) if violated else reports[0]}
        return [_verdict(rule, violated, ev, ctx)]

    return [_verdict(rule, False, [])]


# ---------------------------------------------------------------- 分派表

RULE_DISPATCH = {
    "required_field": check_required_field,
    "timeliness": check_timeliness,
    "cross_consistency": check_cross_consistency,
    "medication_logic": check_medication_logic,
    "lab_logic": check_lab_logic,
    "signature_format": check_signature_format,
    "timeline_logic": check_timeline_logic,
}
