"""知识库测试：blocks 引文逐字回验 raw 原文；rules 全挂 basis 且与 blocks 对齐。

纪律（plan/04 §4 / data/README.md）：查证优先于自证——条文块引文必须是
raw 规范原文的逐字子串；规则依据（文号+条款+引文）必须能对上条文块。
"""

import json
from pathlib import Path

import pytest

from mrqc.knowledge import knowledge_dir
from mrqc.rules import CHECK_TYPES, Rule, RuleEngine, RuleError

REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = knowledge_dir()

# 与 data/README.md 登记表三一致的文号清单（台账口径）
DOCUMENT_NO_RAW = {
    "卫医政发〔2010〕11号": "病历书写基本规范_卫医政发2010-11号.txt",
    "国卫医发〔2018〕8号": "医疗质量安全核心制度要点_国卫医发2018-8号.txt",
    "国卫医发〔2013〕31号": "医疗机构病历管理规定2013年版_国卫医发2013-31号.txt",
    "国卫办医函〔2021〕28号": "病案管理质量控制指标2021年版_文本层.txt",
    "国卫办医发〔2016〕24号": "住院病案首页数据填写质量规范暂行_国卫办医发2016-24号.txt",
}


def _load_json_files(sub):
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((KNOWLEDGE / sub).glob("*.json"))]


def _all_blocks():
    out = []
    for data in _load_json_files("blocks"):
        for blk in data["blocks"]:
            out.append((data["document_no"], data["source_file"], blk))
    return out


def _all_rules():
    out = []
    for data in _load_json_files("rules"):
        out.extend(data["rules"])
    return out


def test_blocks_cover_all_five_documents():
    doc_nos = {d["document_no"] for d in _load_json_files("blocks")}
    assert doc_nos == set(DOCUMENT_NO_RAW)


def test_block_quotes_are_verbatim_substrings_of_raw():
    """防幻觉守门：每条条文块引文必须在其 raw 原文中逐字存在。"""
    for doc_no, source_file, blk in _all_blocks():
        raw = (KNOWLEDGE / source_file).read_text(encoding="utf-8")
        assert blk["quote"] in raw, "引文非原文子串：%s %s" % (doc_no, blk["clause"])
        assert blk["clause"] and blk["block_id"]


def test_rules_load_and_meet_count_floor():
    engine = RuleEngine.load(KNOWLEDGE / "rules")
    assert len(engine.rules) >= 30  # DoD：规则 ≥30 条
    assert len({r.id for r in engine.rules}) == len(engine.rules)  # 无重复 ID


def test_rules_come_from_json_with_basis_object():
    rules = _all_rules()
    assert len(rules) >= 30
    for item in rules:
        basis = item["basis"]
        assert basis.get("document") and basis.get("document_no")
        assert basis.get("clause") and basis.get("quote")
        assert basis["status"] in ("已核对", "待核对")


def test_rule_basis_matches_block_word_for_word():
    """规则依据必须（文号, 条款, 引文）三对一命中条文块——单一来源，不许转写。"""
    block_index = {(doc_no, blk["clause"]): blk["quote"]
                   for doc_no, _, blk in _all_blocks()}
    for item in _all_rules():
        b = item["basis"]
        key = (b["document_no"], b["clause"])
        assert key in block_index, "规则 %s 的依据条款未入库 blocks：%s" % (item["id"], key)
        assert block_index[key] == b["quote"], "规则 %s 引文与 blocks 不一致" % item["id"]
        assert b["document_no"] in DOCUMENT_NO_RAW, "规则 %s 文号不在台账：%s" % (item["id"], b["document_no"])


def test_rules_cover_all_defect_ids():
    """plan/04 §7 缺陷 ID 表 14 个 ID 全部有对应规则，ID 不得改名。"""
    DEFECT_IDS = {
        "F-REQ-01", "F-SIGN-01", "F-TIME-01", "F-TIME-02", "F-TIME-03",
        "C-DIAG-01", "C-SURG-01", "C-SURG-02", "C-LAB-01", "C-LAB-02",
        "C-ORD-01", "C-ANTI-01", "C-BLOOD-01", "C-TIME-01",
    }
    rule_ids = {r["id"] for r in _all_rules()}
    assert DEFECT_IDS <= rule_ids


def test_rules_cover_all_seven_check_types():
    types = {r["type"] for r in _all_rules()}
    assert types == set(CHECK_TYPES)


def test_unverified_basis_rules_use_need_confirm_severity():
    """待核对依据的规则 severity 必须是 NEED_CONFIRM（结论只能待人工确认）。"""
    from mrqc.rules import Severity
    for item in _all_rules():
        if item["basis"]["status"] == "待核对":
            assert item["severity"] == Severity.NEED_CONFIRM.value, item["id"]


def test_no_basis_rule_rejected():
    """无依据规则加载即报错（特性，不是 bug）——真实规则库不得触发。"""
    d = {"id": "X-01", "name": "n", "type": "required_field", "severity": "HIGH",
         "channel": "formal"}
    with pytest.raises(RuleError):
        Rule.from_dict(d)


def test_real_rules_directory_is_loadable_via_engine_check():
    """真实规则库 + 空卡：全规则可执行（不抛 NotImplementedError），空数据不硬判。"""
    from mrqc.models import RecordCard
    engine = RuleEngine.load(KNOWLEDGE / "rules")
    texts = {"手术记录": "手术记录\n术后首次病程记录"}  # 覆盖全部门控关键词
    findings = engine.check(RecordCard(), part_texts=texts)
    assert len(findings) == len(engine.rules)
    assert all(f.status == "pass" for f in findings)
