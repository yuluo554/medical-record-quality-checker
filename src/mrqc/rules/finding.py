"""质控结论与依据模型。

纪律（plan/04 §3）：每条结论必须挂规范依据（文号+条款+摘录）；
severity 四级风险 + 待人工确认独立级别，多值/低置信度不硬判。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..models import Evidence

__all__ = ["Severity", "Basis", "Finding"]


class Severity(str, Enum):
    """缺陷分级：四级风险 + 待人工确认。"""

    LOW = "LOW"  # 低风险
    MEDIUM = "MEDIUM"  # 一般风险
    HIGH = "HIGH"  # 较大风险
    CRITICAL = "CRITICAL"  # 重大风险
    NEED_CONFIRM = "NEED_CONFIRM"  # 待人工确认（非风险级别，独立状态）

    @property
    def label(self) -> str:
        return SEVERITY_LABELS[self]


SEVERITY_LABELS = {
    Severity.LOW: "低风险",
    Severity.MEDIUM: "一般风险",
    Severity.HIGH: "较大风险",
    Severity.CRITICAL: "重大风险",
    Severity.NEED_CONFIRM: "待人工确认",
}


@dataclass
class Basis:
    """规范依据：结论为什么成立。status=待核对 的依据只能产出 NEED_CONFIRM 结论。"""

    document: str  # 文件名，如 "病历书写基本规范"
    document_no: str  # 文号，如 "卫医政发〔2010〕11号"
    clause: str  # 条款定位
    quote: str  # 条文原文摘录
    status: str = "已核对"  # 已核对 | 待核对

    def to_dict(self) -> Dict[str, str]:
        return {
            "document": self.document,
            "document_no": self.document_no,
            "clause": self.clause,
            "quote": self.quote,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Basis":
        return cls(
            document=d.get("document", ""),
            document_no=d.get("document_no", ""),
            clause=d.get("clause", ""),
            quote=d.get("quote", ""),
            status=d.get("status", "已核对"),
        )


@dataclass
class Finding:
    """一条质控结论。status ∈ {pass, fail, need_confirm}。"""

    rule_id: str
    rule_name: str
    severity: Severity
    basis: Optional[Basis] = None
    evidence: List[Evidence] = field(default_factory=list)  # 病历内证据（参数卡摘录）
    suggestion: str = ""  # 整改建议
    status: str = "fail"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "severity_label": self.severity.label,
            "basis": self.basis.to_dict() if self.basis else None,
            "evidence": [e.to_dict() for e in self.evidence],
            "suggestion": self.suggestion,
            "status": self.status,
        }
