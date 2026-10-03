"""合成病历规格：一次住院的全部槽位值（渲染与真值共用的中间层）。

生成流程：build_spec（模板池 + 确定性 RNG）→ RecordSpec
→（注入器可对 RecordSpec 做确定性变异）→ render 渲染六部件文本 + truth 参数卡。
注入变异发生在渲染之前，保证文本与真值永远来自同一份槽位值。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .rng import DetRng

__all__ = ["MedSpec", "LabItemSpec", "LabReportSpec", "SurgerySpec", "RecordSpec",
           "load_templates", "build_spec"]

_BASE_DATE = datetime(2026, 1, 5, 8, 0)

# 合成身份池（姓名为常见组合随机拼合，与真实人物无关；医生池同理）
_PATIENT_NAMES = (
    "陈国强", "林淑芬", "王建国", "赵秀英", "李卫东", "周丽华", "吴志强", "郑爱珍",
    "孙永刚", "马春兰", "朱建军", "胡桂芳", "郭海涛", "何雪梅", "黄文斌", "罗春燕",
    "梁国庆", "宋雅琴", "唐立新", "许凤英", "韩德福", "冯秀兰", "曹振宇", "彭玉华",
    "程晓东", "董玉梅", "袁明辉", "蒋丽萍", "杜长江", "贺明兰",
)
_DOCTOR_NAMES = (
    "张伟", "王芳", "李建国", "刘洋", "陈静", "杨帆", "赵磊", "周敏",
    "吴刚", "郑华", "孙明", "徐丽",
)


@dataclass
class MedSpec:
    """一条用药医嘱槽位。longterm=True 记长期医嘱单，否则临时医嘱单。"""

    drug: str
    dose: str
    dose_unit: str
    route: str
    frequency: str
    start: datetime
    stop: Optional[datetime] = None  # 长期医嘱的停止时间；临时医嘱为 None
    longterm: bool = True
    is_antibiotic: bool = False
    antibiotic_level: str = ""
    is_blood: bool = False


@dataclass
class LabItemSpec:
    """单条检验/检查结果槽位。value 数值型；value_text 文本型（影像/心电图）。"""

    item: str
    value: Optional[str] = None
    value_text: Optional[str] = None
    unit: str = ""
    flag: str = "正常"  # ↑ / ↓ / 正常
    critical: bool = False
    ref: str = ""


@dataclass
class LabReportSpec:
    """一张报告（类别 + 报告时间 + 若干条目）。"""

    category: str  # 血常规 / 血生化 / 影像 / 心电图
    report_time: Optional[datetime] = None
    items: List[LabItemSpec] = field(default_factory=list)


@dataclass
class SurgerySpec:
    """手术槽位（仅外科病种）。performed_name 可被 C-SURG-01 注入改写；
    operator_signed_name 可被 C-SURG-02 注入改写（与术者正文分离）。"""

    performed_name: str
    planned_name: str  # 术前讨论拟施术式（C-SURG-01 的比对锚）
    preop_dx: str
    postop_dx: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    duration_min: int = 0
    surgeon: str = ""
    operator_signed_name: str = ""  # 手术记录尾部"术者签名"行姓名
    assistants: List[str] = field(default_factory=list)
    anesthesia: str = ""
    incision: str = ""
    op_finding: str = ""
    blood_ml: str = ""
    blood_used: bool = False
    blood_approved: bool = False  # 用血审批病程段（C-BLOOD-01 的比对点）
    blood_drug: str = ""
    blood_dose: str = ""
    blood_dose_unit: str = ""


@dataclass
class RecordSpec:
    """一份病历的全部槽位值。"""

    record_id: str = ""
    template_id: str = ""
    template: Dict[str, Any] = field(default_factory=dict)
    hospital_no: str = ""
    name: str = ""
    gender: str = ""
    age: int = 0
    department: str = ""
    bed: int = 0
    admission: Optional[datetime] = None
    discharge: Optional[datetime] = None
    hospital_days: int = 0
    record_time: Optional[datetime] = None  # 入院记录完成时间
    first_course_time: Optional[datetime] = None
    complaint: str = ""
    hpi: str = ""
    past_history: str = ""
    pe: str = ""
    assist_exam: str = ""
    preop_discussion_time: Optional[datetime] = None
    postop_course_time: Optional[datetime] = None
    daily_course_time: Optional[datetime] = None
    daily_course_text: str = ""
    admission_dx: str = ""
    discharge_dx: str = ""
    plan_text: str = ""
    discharge_orders: str = ""
    course_through: str = ""
    meds: List[MedSpec] = field(default_factory=list)
    lab_reports: List[LabReportSpec] = field(default_factory=list)
    critical_value: str = ""  # 危急值检验值（空串=无危急值变体）
    critical_handling_time: Optional[datetime] = None
    critical_handling_text: str = ""
    drop_critical_course: bool = False  # C-LAB-01：删危急值处置病程段
    drop_complaint: bool = False  # F-REQ-01：删主诉段
    drop_signature: str = ""  # F-SIGN-01："attending"（上级审签）| "operator"（术者签名）
    blood_approval_time: Optional[datetime] = None  # 用血审批病程时间（干净用血记录才有）
    surgery: Optional[SurgerySpec] = None
    resident: str = ""
    attending: str = ""
    surgeon: str = ""
    assistants: List[str] = field(default_factory=list)


def load_templates() -> Dict[str, Dict[str, Any]]:
    """加载 data/templates/*.json，按 template_id 索引（文件名序固定保证可复现）。"""
    root = Path(__file__).resolve().parents[3] / "data" / "templates"
    templates: Dict[str, Dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            tpl = json.load(f)
        templates[tpl["template_id"]] = tpl
    if not templates:
        raise FileNotFoundError("未找到病种模板：%s" % root)
    return templates


def _fmt_hm(dt: datetime) -> str:
    return "%04d-%02d-%02d %02d:%02d" % (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def _snap(dt: datetime, minutes: int, rng: DetRng) -> datetime:
    """偏移 minutes 并把分钟取整到 0/15/30/45 槽位。"""
    moved = dt + timedelta(minutes=minutes)
    return moved.replace(minute=rng.minute_slot(), second=0, microsecond=0)


def _fill(tpl_text: str, **vars_: Any) -> str:
    out = tpl_text
    for key, val in vars_.items():
        out = out.replace("{%s}" % key, str(val))
    return out


def _build_meds(rng: DetRng, tpl: Dict[str, Any], admission: datetime,
                discharge: datetime, surgery: Optional[SurgerySpec]) -> List[MedSpec]:
    """从模板池构建用药医嘱（含时间推导）。"""
    meds_cfg = tpl["meds"]
    meds: List[MedSpec] = []
    # 长期抗菌药（主，其余池内抗菌药至多再联用一种）
    ab = rng.choice(meds_cfg["antibiotics"])
    meds.append(MedSpec(
        drug=ab["drug"], dose=ab["dose"], dose_unit=ab["dose_unit"], route=ab["route"],
        frequency=ab["frequency"], longterm=True, is_antibiotic=True,
        antibiotic_level=ab["level"],
        start=_snap(admission, 90, rng), stop=_snap(discharge, -120, rng),
    ))
    for extra in meds_cfg["antibiotics"]:
        if extra["drug"] == ab["drug"]:
            continue
        meds.append(MedSpec(
            drug=extra["drug"], dose=extra["dose"], dose_unit=extra["dose_unit"],
            route=extra["route"], frequency=extra["frequency"], longterm=True,
            is_antibiotic=True, antibiotic_level=extra["level"],
            start=_snap(admission, 105, rng), stop=_snap(discharge, -120, rng),
        ))
        break
    # 非抗菌长期药
    for other in meds_cfg["other"]:
        meds.append(MedSpec(
            drug=other["drug"], dose=other["dose"], dose_unit=other["dose_unit"],
            route=other["route"], frequency=other["frequency"], longterm=True,
            start=_snap(admission, 120, rng), stop=_snap(discharge, -120, rng),
        ))
    # 术前临时用药（外科）
    for pre in meds_cfg.get("preop_temp", []):
        if surgery is not None:
            meds.append(MedSpec(
                drug=pre["drug"], dose=pre["dose"], dose_unit=pre["dose_unit"],
                route=pre["route"], frequency=pre["frequency"], longterm=False,
                start=surgery.start - timedelta(minutes=30),  # type: ignore[operator]
            ))
    # 溶剂类临时医嘱（如 0.9%氯化钠注射液；进入参数卡，M2 解析同源）
    for solvent in meds_cfg.get("solvents", []):
        meds.append(MedSpec(
            drug=solvent["drug"], dose=solvent["dose"], dose_unit=solvent["dose_unit"],
            route=solvent["route"], frequency="", longterm=False,
            start=_snap(admission, 60, rng),
        ))
    # 输血医嘱（用血变体）
    if surgery is not None and surgery.blood_used:
        meds.append(MedSpec(
            drug=surgery.blood_drug, dose=surgery.blood_dose, dose_unit=surgery.blood_dose_unit,
            route="静脉输注", frequency="术中一次", longterm=False, is_blood=True,
            start=surgery.start,  # type: ignore[arg-type]
        ))
    return meds


def build_spec(template: Dict[str, Any], rng: DetRng, hospital_seq: int, record_id: str,
               force_critical: Optional[bool] = None,
               force_blood: Optional[bool] = None) -> RecordSpec:
    """从模板池抽样构建一份干净病历槽位（变体可用 force_* 强制开/关）。"""
    tpl = template
    name = rng.choice(_PATIENT_NAMES)
    gender = rng.choice(("男", "女"))
    age = rng.randint(*tpl["age_range"])
    admission = _BASE_DATE.replace(
        hour=8 + rng.randint(0, 2), minute=rng.minute_slot(), second=0, microsecond=0
    ) + timedelta(days=hospital_seq * 2 + rng.randint(0, 1))

    doctors = rng.pick(_DOCTOR_NAMES, 4)
    resident, attending, surgeon, extra_doctor = doctors
    others = [d for d in _DOCTOR_NAMES if d not in doctors]
    assistant_names = [extra_doctor, rng.choice(others) if others else resident]

    spec = RecordSpec(
        record_id=record_id,
        template_id=tpl["template_id"],
        template=tpl,
        hospital_no="2026%06d" % (700000 + hospital_seq),
        name=name, gender=gender, age=age,
        department=tpl["department"],
        bed=rng.randint(1, 58),
        admission=admission,
        record_time=_snap(admission, rng.randint(30, 120), rng),
        first_course_time=_snap(admission, rng.randint(60, 180), rng),
        resident=resident, attending=attending, surgeon=surgeon,
        assistants=assistant_names,
    )
    spec.discharge = _snap(admission + timedelta(days=rng.randint(5, 8)), 0, rng).replace(hour=10)
    spec.hospital_days = (spec.discharge.date() - spec.admission.date()).days
    spec.past_history = rng.choice(tpl["past_history_pool"])
    spec.assist_exam = tpl["assist_tpl"]

    # 主诉/现病史/查体（模板槽位变量先抽值再填句；全量变量池保证
    # 任一主诉变体与现病史模板共用同一组取值，不残留原始占位符）
    pool_vars = {
        "d": rng.randint(1, 7), "e": rng.randint(1, 12), "h": rng.randint(6, 48),
        "m": rng.randint(3, 24), "v": rng.randint(0, 3),
    }
    comp_cfg = rng.choice(tpl["complaints"])
    comp_vars = {k: pool_vars[k] for k in comp_cfg["vars"]}
    spec.complaint = _fill(comp_cfg["tpl"], **comp_vars)
    hpi_vars = dict(pool_vars)
    hpi_vars.update({"t": "%d.%d" % (rng.randint(37, 39), rng.choice((2, 5, 8)))})
    spec.hpi = _fill(tpl["hpi_tpl"], **hpi_vars)
    spec.pe = _fill(
        tpl["pe_tpl"],
        t="%d.%d" % (rng.randint(36, 38), rng.choice((2, 5, 8))),
        p=str(rng.randint(72, 102)), r=str(rng.randint(16, 22)),
        sbp=str(rng.randint(105, 145)), dbp=str(rng.randint(65, 92)),
    )

    # 诊断
    spec.admission_dx = tpl["admission_dx"]
    spec.discharge_dx = rng.choice(tpl["discharge_dx_pool"])
    spec.plan_text = tpl["first_course"]["plan_tpl"]
    spec.discharge_orders = tpl["discharge_orders"]

    # 危急值变体（内科为主；外科模板 chance=0）
    want_critical = (rng.chance(tpl.get("critical_lab_chance", 0.0))
                     if force_critical is None else force_critical)

    # 手术（外科病种）
    surg_cfg = tpl.get("surgery")
    if surg_cfg:
        start = _snap(admission + timedelta(minutes=rng.randint(*surg_cfg["start_offset_min_range"])), 0, rng)
        duration = rng.randint(*surg_cfg["duration_min_range"])
        blood_variant = bool(tpl.get("transfusion_variant", False))
        blood_used = (rng.chance(0.3) if blood_variant else False) if force_blood is None else force_blood
        blood = tpl.get("blood_product") or {}
        spec.surgery = SurgerySpec(
            performed_name=surg_cfg["name"],
            planned_name=surg_cfg["name"],
            preop_dx=surg_cfg["preop_dx"],
            postop_dx=spec.discharge_dx,
            start=start, end=start + timedelta(minutes=duration), duration_min=duration,
            surgeon=surgeon, operator_signed_name=surgeon,
            assistants=assistant_names,
            anesthesia=rng.choice(surg_cfg["anesthesia_pool"]),
            incision=surg_cfg["incision"],
            op_finding=rng.choice(surg_cfg["finding_pool"]),
            blood_ml=rng.choice(surg_cfg["blood_ml_pool"]),
            blood_used=blood_used,
            blood_approved=blood_used,  # 干净记录：用血必带审批病程段
            blood_drug=blood.get("drug", ""),
            blood_dose=blood.get("dose", ""),
            blood_dose_unit=blood.get("dose_unit", ""),
        )
        spec.preop_discussion_time = _snap(start - timedelta(minutes=rng.randint(120, 240)), 0, rng)
        spec.postop_course_time = _snap((start + timedelta(minutes=duration))
                                        + timedelta(minutes=rng.randint(30, 90)), 0, rng)
        spec.discharge = _snap(start + timedelta(minutes=duration + rng.randint(2880, 4320)), 0, rng).replace(hour=10)
        spec.hospital_days = (spec.discharge.date() - spec.admission.date()).days
        spec.daily_course_time = _snap(start + timedelta(minutes=1440 + rng.randint(30, 180)), 0, rng)
        if spec.surgery.blood_used and spec.surgery.blood_approved:
            spec.blood_approval_time = _snap((start + timedelta(minutes=duration))
                                             + timedelta(minutes=rng.randint(60, 120)), 0, rng)
    else:
        spec.daily_course_time = _snap(admission + timedelta(days=2, minutes=rng.randint(30, 240)), 0, rng)
    spec.daily_course_text = rng.choice(tpl["daily_course_pool"])

    # 危急值：报告时间与"血生化"报告对齐，处置病程在报告后 30 分钟
    crit_category = tpl["critical_category"]
    crit_item = tpl["critical_item"]
    crit_value = ""
    crit_time = None
    if want_critical:
        for entry in tpl["labs"]:
            if entry["category"] == crit_category:
                crit_time = _snap(admission + timedelta(minutes=rng.randint(*entry["report_offset_min"])), 0, rng)
                for item in entry["items"]:
                    if item["item"] == crit_item and item.get("critical_pool"):
                        crit_value = rng.choice(item["critical_pool"])
        spec.critical_handling_time = _snap(crit_time + timedelta(minutes=30), 0, rng) if crit_time else None
        spec.critical_handling_text = _fill(tpl["critical_handling_tpl"], v=crit_value or "2.8")
    spec.critical_value = crit_value

    # 检验报告
    for entry in tpl["labs"]:
        report_time = crit_time if (want_critical and entry["category"] == crit_category and crit_time) \
            else _snap(admission + timedelta(minutes=rng.randint(*entry["report_offset_min"])), 0, rng)
        report = LabReportSpec(category=entry["category"], report_time=report_time)
        for item in entry["items"]:
            if want_critical and entry["category"] == crit_category and item["item"] == crit_item \
                    and item.get("critical_pool"):
                report.items.append(LabItemSpec(
                    item=item["item"], value=crit_value, unit=item["unit"],
                    flag="↓", critical=True, ref=item["ref"],
                ))
            elif "value_text_pool" in item:
                report.items.append(LabItemSpec(item=item["item"], value_text=rng.choice(item["value_text_pool"])))
            else:
                report.items.append(LabItemSpec(
                    item=item["item"], value=rng.choice(item["pool"]),
                    unit=item["unit"], flag=item["flag"], ref=item["ref"],
                ))
        spec.lab_reports.append(report)

    # 医嘱（在最终出院时间确定后构建）
    spec.meds = _build_meds(rng, tpl, admission, spec.discharge, spec.surgery)
    return spec
