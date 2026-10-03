"""规则层测试：无依据规则拒绝加载、门控对 check_type 生效、空规则库行为。"""

import pytest

from mrqc.models import RecordCard
from mrqc.rules import Basis, Rule, RuleEngine, RuleError, Severity


def _rule_dict(**overrides):
    base = {
        "id": "C-DIAG-01",
        "name": "出院诊断与用药医嘱匹配",
        "type": "cross_consistency",
        "severity": "HIGH",
        "channel": "integrity",
        "basis": {
            "document": "医疗质量安全核心制度要点",
            "document_no": "国卫医发〔2018〕8号",
            "clause": "病历管理制度",
            "quote": "客观、真实、准确、及时、完整、规范",
            "status": "已核对",
        },
        "only_if": {"any_keyword": ["出院记录"]},
        "params": {},
        "suggestion_template": "请核对出院诊断与用药。",
    }
    base.update(overrides)
    return base


def test_rule_requires_basis():
    d = _rule_dict()
    del d["basis"]
    with pytest.raises(RuleError, match="basis"):
        Rule.from_dict(d)


def test_rule_rejects_unknown_type_and_severity():
    with pytest.raises(RuleError, match="check_type"):
        Rule.from_dict(_rule_dict(type="magic_check"))
    with pytest.raises(RuleError, match="severity"):
        Rule.from_dict(_rule_dict(severity="超重大风险"))


def test_rule_ok():
    rule = Rule.from_dict(_rule_dict())
    assert rule.severity is Severity.HIGH
    assert rule.basis.document_no == "国卫医发〔2018〕8号"


def test_engine_load_empty_dir(tmp_path):
    engine = RuleEngine.load(tmp_path)  # 目录不存在
    assert engine.rules == []
    (tmp_path / "rules").mkdir()
    engine = RuleEngine.load(tmp_path / "rules")  # 空目录
    assert engine.rules == []


def test_engine_gate_blocks_rule():
    """only_if 门控：关键词不出现则规则不启用（对全部 check_type 生效）。"""
    engine = RuleEngine(rules=[Rule.from_dict(_rule_dict())])
    card = RecordCard()
    # 部件原文无"出院记录"关键词 → 门控拦截，不产出结论
    assert engine.check(card, part_texts={"手术记录": "手术经过顺利"}) == []
    # 关键词出现 → 进入分派执行检查（M3 起七类检查函数全部注册，不再 NotImplementedError）
    findings = engine.check(card, part_texts={"出院记录": "出院记录：患者于 2026-03-02 治愈出院。"})
    assert len(findings) == 1
    assert findings[0].rule_id == "C-DIAG-01"


def test_engine_dispatch_covers_all_check_types():
    """七类 check_type 全部注册检查函数（M3 完成，未知类型仍显式暴露）。"""
    from mrqc.rules import CHECK_TYPES
    engine = RuleEngine()
    assert set(engine._dispatch) == set(CHECK_TYPES)


def test_engine_no_rules_no_findings():
    engine = RuleEngine()
    assert engine.check(RecordCard()) == []
