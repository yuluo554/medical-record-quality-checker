"""兜底抽取管线单测（M4，全离线：client 注入 mock，零 API 依赖）。

覆盖：低置信触发（仅 confidence<阈值）、候选行压缩、quote 逐字回验丢弃、
数值/时间合法性丢弃、白名单越权丢弃、全部降级路径（未配置/LLMError/JSON 损坏/
结构不合契约）参数卡原样不动、CLI check 接线（配置了 mock 通路 / 未配置零调用）。
"""

import json
from pathlib import Path

import pytest

from mrqc.cli import main
from mrqc.llm.client import (
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    LLMError,
)
from mrqc.llm.fallback import (
    EXTRACT_CONFIDENCE,
    MAX_CANDIDATE_LINES,
    MAX_LINES_PER_PART,
    apply_fallback,
    candidate_lines,
    low_confidence_fields,
)
from mrqc.models import Evidence, FieldValue, LabResult, PatientInfo, RecordCard

REPO_ROOT = Path(__file__).resolve().parents[1]

_LABS_TEXT = (
    "检验检查报告\n"
    "【影像】\n"
    "报告时间：2026-09-30 08:00\n"
    "检查所见：双肺纹理增粗，未见明显实变。\n"
)
PART_TEXTS = {"检验检查报告": _LABS_TEXT}


def _low_conf_card():
    """构造低置信场景（仿 labs 文本型 item_name confidence=0.6 既有模式）。"""
    card = RecordCard()
    card.labs.append(LabResult(
        item_name=FieldValue(value="影像", confidence=0.6,
                             evidence=[Evidence(part="检验检查报告",
                                                quote="检查所见：双肺纹理增粗，未见明显实变。")]),
        value_text=FieldValue(value="双肺纹理增粗，未见明显实变。",
                              evidence=[Evidence(part="检验检查报告",
                                                 quote="检查所见：双肺纹理增粗，未见明显实变。")]),
    ))
    return card


class MockClient:
    """测试注入：记录 chat 调用，返回预置回复或抛预置异常。"""

    def __init__(self, reply=None, error=None, raw=""):
        self.calls = []
        self.reply = reply
        self.error = error
        self.raw = raw

    def chat(self, messages, json_mode=True, **kw):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        if self.raw:
            return self.raw
        return json.dumps(self.reply, ensure_ascii=False)


def _reply(*extractions):
    return {"extractions": list(extractions)}


# ---------------------------------------------------------------- 触发与压缩

def test_only_low_confidence_fields_trigger():
    card = _low_conf_card()
    card.labs.append(LabResult(
        item_name=FieldValue(value="白细胞计数", confidence=1.0,
                             evidence=[Evidence(part="检验检查报告", quote="x")]),
    ))
    refs = low_confidence_fields(card, 0.8)
    assert [r.path for r in refs] == ["labs[0].item_name"]  # 1.0 字段不触发


def test_threshold_param_controls_trigger():
    card = _low_conf_card()
    assert low_confidence_fields(card, 0.5) == []  # 阈值以下才触发
    assert low_confidence_fields(card, 0.6) == []  # 严格小于：=阈值不触发
    assert len(low_confidence_fields(card, 0.7)) == 1


def test_high_confidence_card_skips_llm_entirely():
    card = RecordCard(patient=PatientInfo(name=FieldValue(value="张三")))
    mock = MockClient(reply=_reply())
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert mock.calls == []  # 无低置信字段不得发起 LLM 调用
    assert stats["n_low_conf"] == 0


def test_candidate_lines_compression():
    text = "\n".join([
        "入院记录",
        "姓名：张三",
        "主诉：咳嗽咳痰 3 天。",  # 含数字 → 保留
        "这段是完全无关的抒情文字。",  # 无数字无关键词 → 丢弃
        "既往体健。",
    ])
    out = candidate_lines({"入院记录": text})
    assert "姓名：张三" in out
    assert "咳嗽咳痰 3 天" in out
    assert "抒情文字" not in out


def test_candidate_lines_caps():
    lines = ["检查所见：第 %d 层未见异常。" % i for i in range(MAX_LINES_PER_PART + 20)]
    out = candidate_lines({"检验检查报告": "\n".join(lines)})
    assert out.count("检查所见") == MAX_LINES_PER_PART  # 单部件限量


def test_candidate_lines_total_cap():
    part = "\n".join("床号 %d" % i for i in range(MAX_LINES_PER_PART))
    texts = {"入院记录": part, "病程记录": part, "出院记录": part, "医嘱单": part}
    out = candidate_lines(texts, parts=set(texts))
    assert out.count("床号") <= MAX_CANDIDATE_LINES  # 总量上限


# ---------------------------------------------------------------- 回验与写回

def test_happy_path_applies_extraction():
    card = _low_conf_card()
    mock = MockClient(reply=_reply({
        "field": "labs[0].item_name",
        "source_part": "检验检查报告",
        "quote": "检查所见：双肺纹理增粗，未见明显实变。",
        "value": "胸部正位片",
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_applied"] == 1 and stats["n_low_conf"] == 1
    fv = card.labs[0].item_name
    assert fv.value == "胸部正位片"
    assert fv.confidence == EXTRACT_CONFIDENCE
    assert fv.evidence[0].quote in PART_TEXTS["检验检查报告"]  # 写回证据仍逐字
    # 请求里带上了候选行与字段清单
    user_msg = mock.calls[0][1]["content"]
    assert "labs[0].item_name" in user_msg
    assert "[检验检查报告]" in user_msg


def test_hallucinated_quote_dropped():
    card = _low_conf_card()
    before = card.labs[0].item_name.to_dict()
    mock = MockClient(reply=_reply({
        "field": "labs[0].item_name", "source_part": "检验检查报告",
        "quote": "本报告由AI自动生成，项目名称：胸部正位片",  # 非原文子串
        "value": "胸部正位片",
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_dropped_quote"] == 1 and stats["n_applied"] == 0
    assert card.labs[0].item_name.to_dict() == before  # 参数卡原样不动


def test_partial_quote_dropped():
    """quote 多了一个字（非逐字连续子串）→ 丢弃。"""
    card = _low_conf_card()
    mock = MockClient(reply=_reply({
        "field": "labs[0].item_name", "source_part": "检验检查报告",
        "quote": "检查所见：双肺纹理增粗，未见明显实变。报告清晰。",
        "value": "胸部正位片",
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_dropped_quote"] == 1 and stats["n_applied"] == 0


def test_numeric_range_dropped():
    card = _low_conf_card()
    card.labs[0].value = FieldValue(value=None, confidence=0.6)
    mock = MockClient(reply=_reply({
        "field": "labs[0].value", "source_part": "检验检查报告",
        "quote": "检查所见：双肺纹理增粗，未见明显实变。",
        "value": 99999,  # 超生理范围
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_dropped_range"] == 1 and stats["n_applied"] == 0
    assert card.labs[0].value.value is None


def test_numeric_string_converted_and_applied():
    card = _low_conf_card()
    card.labs[0].value = FieldValue(value=None, confidence=0.6)
    mock = MockClient(reply=_reply({
        "field": "labs[0].value", "source_part": "检验检查报告",
        "quote": "检查所见：双肺纹理增粗，未见明显实变。",
        "value": "130",  # 数值字符串 → 规整为数字
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_applied"] == 1
    assert card.labs[0].value.value == 130


def test_time_format_dropped():
    card = _low_conf_card()
    card.labs[0].report_time = FieldValue(value=None, confidence=0.6)
    mock = MockClient(reply=_reply({
        "field": "labs[0].report_time", "source_part": "检验检查报告",
        "quote": "报告时间：2026-09-30 08:00",
        "value": "2026年9月30日",  # 时间格式非法
    }))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_dropped_range"] == 1 and stats["n_applied"] == 0


def test_unknown_field_and_part_dropped():
    card = _low_conf_card()
    mock = MockClient(reply=_reply(
        {"field": "labs[5].item_name", "source_part": "检验检查报告",
         "quote": "检查所见：双肺纹理增粗，未见明显实变。", "value": "x"},  # 未请求
        {"field": "labs[0].item_name", "source_part": "手术记录",
         "quote": "检查所见", "value": "x"},  # 部件不在 part_texts
    ))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["n_dropped_other"] == 2 and stats["n_applied"] == 0


def test_knowledge_derived_fields_not_requested():
    """知识派生/结构键不在白名单：低置信的 is_critical 之类不会被送 LLM。"""
    card = _low_conf_card()
    card.labs[0].is_critical = FieldValue(value=True, confidence=0.3)
    refs = low_confidence_fields(card, 0.8)
    assert all(r.leaf not in ("is_critical", "icd10", "purpose") for r in refs)


# ---------------------------------------------------------------- 降级路径

def test_unconfigured_env_degrades(monkeypatch):
    for key in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL):
        monkeypatch.delenv(key, raising=False)
    card = _low_conf_card()
    stats = apply_fallback(card, PART_TEXTS)  # 不传 client → 走环境检查
    assert stats["available"] is False
    assert "未配置" in stats["reason"]
    assert card.labs[0].item_name.value == "影像"  # 卡原样不动


def test_llm_error_degrades_to_rule_path():
    card = _low_conf_card()
    mock = MockClient(error=LLMError("LLM 调用重试耗尽（共 3 次尝试）：网络错误或超时"))
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert stats["available"] is True  # 配置在，但调用失败
    assert "降级纯规则通路" in stats["reason"]
    assert card.labs[0].item_name.value == "影像"


def test_corrupted_json_degrades():
    card = _low_conf_card()
    mock = MockClient(raw="这不是 JSON，模型跑飞了。")
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert "JSON 解析失败" in stats["reason"]
    assert card.labs[0].item_name.value == "影像"


def test_structural_mismatch_degrades():
    card = _low_conf_card()
    mock = MockClient(reply={"结果": "其它结构"})
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert "extractions" in stats["reason"]
    assert stats["n_applied"] == 0


def test_truncated_json_from_mock_degrades():
    """客户端截断修复也救不了（首个对象没闭合）→ JSON 解析失败 → 降级。"""
    card = _low_conf_card()
    mock = MockClient(raw='{"extractions": [{"field": "labs[0]')  # MockClient 不走修复
    stats = apply_fallback(card, PART_TEXTS, client=mock)
    assert "JSON 解析失败" in stats["reason"]


# ---------------------------------------------------------------- CLI 接线

def test_cli_check_with_llm_configured_mock(monkeypatch, capsys):
    """配置齐全 + mock 传输层：check 全链路走 LLM 兜底后仍正常出结论。"""
    monkeypatch.setenv(ENV_BASE_URL, "http://mock/v1")
    monkeypatch.setenv(ENV_API_KEY, "k")
    monkeypatch.setenv(ENV_MODEL, "qwen-plus")
    monkeypatch.setattr("mrqc.llm.client._http_post_json",
                        lambda *a: {"choices": [{"message": {"content": '{"extractions": []}'}}]})
    rc = main(["check", "--input", str(REPO_ROOT / "data" / "samples" / "cap_001")])
    assert rc == 0
    assert "[LLM兜底]" in capsys.readouterr().err  # 兜底节点确实执行


def test_cli_check_unconfigured_never_calls_http(monkeypatch, capsys):
    for key in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL):
        monkeypatch.delenv(key, raising=False)

    def must_not_call(*a):
        raise AssertionError("未配置时不得发起 HTTP 调用")

    monkeypatch.setattr("mrqc.llm.client._http_post_json", must_not_call)
    rc = main(["check", "--input", str(REPO_ROOT / "data" / "samples" / "cap_001")])
    assert rc == 0  # 纯规则通路照常
