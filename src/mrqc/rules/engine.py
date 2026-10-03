"""质控规则引擎骨架。

- 规则 JSON 化（schema 见 plan/04 §3），引擎按 check_type 分派到确定性校验函数；
- only_if 关键词门控对全部 check_type 生效（防跨类目误查）；
- 无依据（basis）的规则拒绝加载——"无出处的规则不得落库"。

检查函数本体在 M3 实现（对照 plan/04 §7 缺陷 ID 表）。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..models import RecordCard
from .finding import Basis, Finding, Severity

__all__ = ["CHECK_TYPES", "RuleError", "Rule", "RuleEngine"]

CHECK_TYPES = (
    "required_field",  # 必填项存在性
    "timeliness",  # 书写时效性
    "cross_consistency",  # 跨文档/跨区块一致性
    "medication_logic",  # 用药规则（抗菌药物分级、用血审核）
    "lab_logic",  # 检验/危急值闭环
    "signature_format",  # 签名/资质/格式
    "timeline_logic",  # 时间轴逻辑矛盾
)

CHANNELS = ("formal", "integrity")  # 形式质控 | 内涵质控


class RuleError(ValueError):
    """规则文件不合法（缺依据/未知类型/未知级别等），加载期即拒绝。"""


@dataclass
class Rule:
    """一条机器可读质控规则（schema 见 plan/04 §3）。"""

    id: str
    name: str
    type: str  # CHECK_TYPES 之一
    severity: Severity
    channel: str  # CHANNELS 之一
    basis: Basis  # 必填：无依据不得落库
    only_if: Dict[str, object] = field(default_factory=dict)  # 门控，如 {"any_keyword": [...]}
    params: Dict[str, object] = field(default_factory=dict)
    suggestion_template: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "Rule":
        rid = str(d.get("id", "")).strip()
        if not rid:
            raise RuleError("规则缺少 id")
        rtype = str(d.get("type", ""))
        if rtype not in CHECK_TYPES:
            raise RuleError("规则 %s 的 check_type 未知：%r" % (rid, rtype))
        channel = str(d.get("channel", ""))
        if channel not in CHANNELS:
            raise RuleError("规则 %s 的 channel 未知：%r" % (rid, channel))
        try:
            severity = Severity(str(d.get("severity", "")))
        except ValueError:
            raise RuleError("规则 %s 的 severity 未知：%r" % (rid, d.get("severity")))
        raw_basis = d.get("basis")
        if not isinstance(raw_basis, dict) or not raw_basis.get("document"):
            # 纪律：没有规范依据的规则不允许进入引擎
            raise RuleError("规则 %s 缺少 basis（文号+条款+摘录），拒绝加载" % rid)
        basis = Basis.from_dict(raw_basis)
        only_if = d.get("only_if") or {}
        params = d.get("params") or {}
        if not isinstance(only_if, dict) or not isinstance(params, dict):
            raise RuleError("规则 %s 的 only_if/params 必须是对象" % rid)
        return cls(
            id=rid,
            name=str(d.get("name", "")),
            type=rtype,
            severity=severity,
            channel=channel,
            basis=basis,
            only_if=only_if,
            params=params,
            suggestion_template=str(d.get("suggestion_template", "")),
        )


class RuleEngine:
    """规则引擎：门控 → type 分派 → 确定性校验。"""

    def __init__(self, rules: Optional[List[Rule]] = None) -> None:
        self.rules: List[Rule] = list(rules or [])
        self._dispatch: Dict[str, Callable[[Rule, RecordCard, dict], List[Finding]]] = {}

    @classmethod
    def load(cls, rules_dir: Path) -> "RuleEngine":
        """加载 data/knowledge/rules/*.json；目录缺失/为空 → 0 条规则（M1/M3 填充）。"""
        rules: List[Rule] = []
        if rules_dir.is_dir():
            for path in sorted(rules_dir.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("rules", [data])
                for item in items:
                    rules.append(Rule.from_dict(item))
        return cls(rules)

    def check(self, card: RecordCard, part_texts: Optional[Dict[str, str]] = None) -> List[Finding]:
        """对参数卡执行全部规则。part_texts：部件名 → 原文，供门控与摘录回验。"""
        texts = part_texts or {}
        findings: List[Finding] = []
        for rule in self.rules:
            if not self._gate_pass(rule, texts):
                continue
            handler = self._dispatch.get(rule.type)
            if handler is None:
                # 检查函数本体 M3 实现；此处显式暴露而非静默吞掉
                raise NotImplementedError(
                    "check_type=%r 的检查函数尚未实现（M3）" % rule.type
                )
            findings.extend(handler(rule, card, texts))
        return findings

    def _gate_pass(self, rule: Rule, part_texts: Dict[str, str]) -> bool:
        """only_if 门控：any_keyword 任一关键词出现在任一部件原文中才启用本规则。

        门控对全部 check_type 生效；空 only_if 视为无条件启用。
        """
        keywords = rule.only_if.get("any_keyword") if rule.only_if else None
        if not keywords:
            return True
        blob = "\n".join(part_texts.values())
        return any(k in blob for k in keywords)
