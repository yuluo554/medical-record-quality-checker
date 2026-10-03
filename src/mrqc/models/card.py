"""病历参数卡：统一中间表示（项目唯一契约）。

六类病历部件（入院/病程/手术/出院/医嘱/检验）解析后全部归入一张参数卡；
真值生成器产出同形状 truth.json；规则引擎只读参数卡；Web 展示参数卡。
改本 schema 必须同步：真值生成器（M1）、解析 F1 基准（M2/M4）、Web 面板（M5）。

所有字段统一用 :class:`FieldValue` 包装：值 + 单位 + 置信度 + 证据列表。
证据摘录必须是部件原文的逐字子串（防幻觉纪律，LLM 兜底同样遵守）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "Evidence",
    "FieldValue",
    "PatientInfo",
    "Diagnosis",
    "Surgery",
    "MedicationOrder",
    "LabResult",
    "TimelineEvent",
    "Signature",
    "RecordCard",
]


@dataclass
class Evidence:
    """证据：字段值来自哪个部件的哪句原文。"""

    part: str  # 部件名，如 "出院记录"
    quote: str  # 原文摘录（逐字）

    def to_dict(self) -> Dict[str, str]:
        return {"part": self.part, "quote": self.quote}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Evidence":
        return cls(part=d.get("part", ""), quote=d.get("quote", ""))


@dataclass
class FieldValue:
    """统一字段包装：值 + 单位 + 置信度 + 证据。"""

    value: Any
    unit: str = ""
    confidence: float = 1.0
    evidence: List[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence 必须在 [0, 1] 内，收到 %r" % self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "evidence": [e.to_dict() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FieldValue":
        return cls(
            value=d.get("value"),
            unit=d.get("unit", ""),
            confidence=float(d.get("confidence", 1.0)),
            evidence=[Evidence.from_dict(e) for e in d.get("evidence", [])],
        )


def _fv(d: Optional[Dict[str, Any]]) -> Optional[FieldValue]:
    return FieldValue.from_dict(d) if d is not None else None


def _fv_list(items: Any) -> List[FieldValue]:
    return [FieldValue.from_dict(x) for x in (items or [])]


@dataclass
class PatientInfo:
    """患者基本信息（全部合成，不使用真实身份）。"""

    name: Optional[FieldValue] = None
    gender: Optional[FieldValue] = None
    age: Optional[FieldValue] = None  # value: 岁；unit: "岁"
    department: Optional[FieldValue] = None
    bed: Optional[FieldValue] = None
    admission_date: Optional[FieldValue] = None  # "YYYY-MM-DD HH:MM"
    discharge_date: Optional[FieldValue] = None
    hospital_days: Optional[FieldValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: (v.to_dict() if v is not None else None) for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PatientInfo":
        kw = {k: _fv(d.get(k)) for k in cls.__dataclass_fields__}
        return cls(**kw)


@dataclass
class Diagnosis:
    """诊断。type ∈ {入院, 出院, 术前, 术后}；出院诊断是跨文档比对的锚点。"""

    type: str
    name: Optional[FieldValue] = None
    icd10: Optional[FieldValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name.to_dict() if self.name else None,
            "icd10": self.icd10.to_dict() if self.icd10 else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Diagnosis":
        return cls(
            type=d.get("type", ""),
            name=_fv(d.get("name")),
            icd10=_fv(d.get("icd10")),
        )


@dataclass
class Surgery:
    """手术信息。与术前讨论/知情同意/签名逐项比对。"""

    name: Optional[FieldValue] = None
    start_time: Optional[FieldValue] = None
    duration_min: Optional[FieldValue] = None  # unit: "分钟"
    surgeon: Optional[FieldValue] = None  # 术者
    assistants: List[FieldValue] = field(default_factory=list)  # 助手
    anesthesia: Optional[FieldValue] = None  # 麻醉方式
    incision_healing: Optional[FieldValue] = None  # 切口愈合等级，如 "Ⅱ/甲"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name.to_dict() if self.name else None,
            "start_time": self.start_time.to_dict() if self.start_time else None,
            "duration_min": self.duration_min.to_dict() if self.duration_min else None,
            "surgeon": self.surgeon.to_dict() if self.surgeon else None,
            "assistants": [a.to_dict() for a in self.assistants],
            "anesthesia": self.anesthesia.to_dict() if self.anesthesia else None,
            "incision_healing": self.incision_healing.to_dict() if self.incision_healing else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Surgery":
        return cls(
            name=_fv(d.get("name")),
            start_time=_fv(d.get("start_time")),
            duration_min=_fv(d.get("duration_min")),
            surgeon=_fv(d.get("surgeon")),
            assistants=_fv_list(d.get("assistants")),
            anesthesia=_fv(d.get("anesthesia")),
            incision_healing=_fv(d.get("incision_healing")),
        )


@dataclass
class MedicationOrder:
    """用药医嘱（长期+临时合并归此）。抗菌药物字段供分级管理规则使用。"""

    drug_name: Optional[FieldValue] = None
    dose: Optional[FieldValue] = None
    dose_unit: Optional[FieldValue] = None  # 如 "g" / "mg" / "ml"
    route: Optional[FieldValue] = None  # 给药途径，如 "静脉滴注"
    frequency: Optional[FieldValue] = None  # 频次，如 "q8h"
    start_time: Optional[FieldValue] = None
    stop_time: Optional[FieldValue] = None
    is_antibiotic: Optional[FieldValue] = None  # bool
    antibiotic_level: Optional[FieldValue] = None  # 非限制/限制/特殊使用级
    purpose: Optional[FieldValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug_name": self.drug_name.to_dict() if self.drug_name else None,
            "dose": self.dose.to_dict() if self.dose else None,
            "dose_unit": self.dose_unit.to_dict() if self.dose_unit else None,
            "route": self.route.to_dict() if self.route else None,
            "frequency": self.frequency.to_dict() if self.frequency else None,
            "start_time": self.start_time.to_dict() if self.start_time else None,
            "stop_time": self.stop_time.to_dict() if self.stop_time else None,
            "is_antibiotic": self.is_antibiotic.to_dict() if self.is_antibiotic else None,
            "antibiotic_level": self.antibiotic_level.to_dict() if self.antibiotic_level else None,
            "purpose": self.purpose.to_dict() if self.purpose else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MedicationOrder":
        return cls(
            drug_name=_fv(d.get("drug_name")),
            dose=_fv(d.get("dose")),
            dose_unit=_fv(d.get("dose_unit")),
            route=_fv(d.get("route")),
            frequency=_fv(d.get("frequency")),
            start_time=_fv(d.get("start_time")),
            stop_time=_fv(d.get("stop_time")),
            is_antibiotic=_fv(d.get("is_antibiotic")),
            antibiotic_level=_fv(d.get("antibiotic_level")),
            purpose=_fv(d.get("purpose")),
        )


@dataclass
class LabResult:
    """检验/检查结果。危急值（is_critical）供报告闭环规则使用。"""

    item_name: Optional[FieldValue] = None
    value: Optional[FieldValue] = None  # 数值型结果
    value_text: Optional[FieldValue] = None  # 文本型结果（如 "未见异常"）
    unit: Optional[FieldValue] = None
    abnormal_flag: Optional[FieldValue] = None  # "↑" / "↓" / "正常"
    is_critical: Optional[FieldValue] = None  # bool，危急值
    report_time: Optional[FieldValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_name": self.item_name.to_dict() if self.item_name else None,
            "value": self.value.to_dict() if self.value else None,
            "value_text": self.value_text.to_dict() if self.value_text else None,
            "unit": self.unit.to_dict() if self.unit else None,
            "abnormal_flag": self.abnormal_flag.to_dict() if self.abnormal_flag else None,
            "is_critical": self.is_critical.to_dict() if self.is_critical else None,
            "report_time": self.report_time.to_dict() if self.report_time else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LabResult":
        return cls(
            item_name=_fv(d.get("item_name")),
            value=_fv(d.get("value")),
            value_text=_fv(d.get("value_text")),
            unit=_fv(d.get("unit")),
            abnormal_flag=_fv(d.get("abnormal_flag")),
            is_critical=_fv(d.get("is_critical")),
            report_time=_fv(d.get("report_time")),
        )


@dataclass
class TimelineEvent:
    """病程关键时间节点。

    event 词汇表（M1 扩展，见 plan/06 决策记录）：
      临床事件：入院 / 术前讨论 / 知情同意 / 手术 / 术后首次病程 / 出院
      记录完成类（供 F-TIME-* 时效规则）：入院记录完成 / 首次病程记录
      处置闭环类（供 C-LAB-01 / C-BLOOD-01）：危急值处置 / 用血审批

    detail：事件附带的比对要点（纯文本，无证据包装）。
    术前讨论事件固定存"拟施手术名称"，供 C-SURG-01 与手术记录术式比对。
    """

    event: str
    time: Optional[FieldValue] = None
    source_part: str = ""  # 时间取自哪个部件
    detail: str = ""  # 比对要点（如术前讨论的拟施术式名）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "time": self.time.to_dict() if self.time else None,
            "source_part": self.source_part,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimelineEvent":
        return cls(
            event=d.get("event", ""),
            time=_fv(d.get("time")),
            source_part=d.get("source_part", ""),
            detail=d.get("detail", ""),
        )


@dataclass
class Signature:
    """签名。role ∈ {住院医师, 主治医师, 主任(副主任)医师, 术者, 上级审签}。"""

    role: str
    name: Optional[FieldValue] = None
    date: Optional[FieldValue] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "name": self.name.to_dict() if self.name else None,
            "date": self.date.to_dict() if self.date else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Signature":
        return cls(
            role=d.get("role", ""),
            name=_fv(d.get("name")),
            date=_fv(d.get("date")),
        )


@dataclass
class RecordCard:
    """病历参数卡：一次质控的全部结构化上下文。"""

    patient: PatientInfo = field(default_factory=PatientInfo)
    diagnoses: List[Diagnosis] = field(default_factory=list)
    surgeries: List[Surgery] = field(default_factory=list)
    medications: List[MedicationOrder] = field(default_factory=list)
    labs: List[LabResult] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    signatures: List[Signature] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)  # 解析告警（无法识别的行等）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient": self.patient.to_dict(),
            "diagnoses": [x.to_dict() for x in self.diagnoses],
            "surgeries": [x.to_dict() for x in self.surgeries],
            "medications": [x.to_dict() for x in self.medications],
            "labs": [x.to_dict() for x in self.labs],
            "timeline": [x.to_dict() for x in self.timeline],
            "signatures": [x.to_dict() for x in self.signatures],
            "parse_warnings": list(self.parse_warnings),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RecordCard":
        return cls(
            patient=PatientInfo.from_dict(d.get("patient", {})),
            diagnoses=[Diagnosis.from_dict(x) for x in d.get("diagnoses", [])],
            surgeries=[Surgery.from_dict(x) for x in d.get("surgeries", [])],
            medications=[MedicationOrder.from_dict(x) for x in d.get("medications", [])],
            labs=[LabResult.from_dict(x) for x in d.get("labs", [])],
            timeline=[TimelineEvent.from_dict(x) for x in d.get("timeline", [])],
            signatures=[Signature.from_dict(x) for x in d.get("signatures", [])],
            parse_warnings=list(d.get("parse_warnings", [])),
        )
