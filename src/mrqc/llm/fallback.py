"""低置信度字段 LLM 兜底抽取管线（M4，plan/03 §5 职责白名单第一项）。

触发条件：仅 ``FieldValue.confidence < 阈值`` 的字段。解析层规则优先路径恒 1.0，
既有低置信场景 = labs 文本型检查行 item_name 0.6（项目名不落部件文本，M2 遗留
语义缺口，正是兜底的目标场景）；测试可按同模式构造低置信字段。

流程（防幻觉三件套，plan/03 §4.5）：
1. 低置信字段定位（白名单叶子，知识派生/结构键不可兜底）；
2. 候选行压缩：只送含数字/领域关键词的行（部件限量 + 总量上限，控成本）；
3. LLM 抽取（客户端 json_mode，截断修复见 client.py）；
4. 逐条回验后写回：契约键齐全 → field 必须在本次请求集内（防越权写入）→
   source_part 必须是已知部件 → **quote 必须是该部件原文的逐字连续子串，
   否则丢弃** → 数值叶子做类型与合法性范围校验（超生理/药理范围丢弃）、
   时间叶子做格式校验；
5. 写回 = value + evidence(逐字摘录) + confidence=EXTRACT_CONFIDENCE（≥触发
   阈值：重复跑不会回环再触发）。

降级纪律：未配置 / LLMError（超时、重试耗尽、JSON 不可解析）/ JSON 损坏 /
结构不合契约 → 参数卡原样不动、返回带 reason 的统计，主流程走纯规则通路。
本管线只补字段值，不做任何质控判定；基准零 API 依赖（未配置即等效纯规则）。
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from ..models import Evidence, FieldValue
from .client import ENV_API_KEY, ENV_BASE_URL, ENV_MODEL, LLMClient, LLMError, llm_available

__all__ = [
    "CONF_THRESHOLD", "EXTRACT_CONFIDENCE", "FieldRef", "apply_fallback",
    "low_confidence_fields", "candidate_lines", "build_messages",
]

ENV_CONF_THRESHOLD = "MRQC_LLM_CONF_THRESHOLD"
CONF_THRESHOLD = 0.8  # 触发阈值：confidence < 0.8 才兜底
EXTRACT_CONFIDENCE = 0.8  # LLM 写回标记（= 阈值，不回环触发；区别于规则解析的 1.0）
MAX_LINES_PER_PART = 80  # 单部件候选行上限
MAX_CANDIDATE_LINES = 240  # 全部部件候选行总量上限

# 可兜底叶子白名单。排除：结构键（type/role/event/detail/source_part）、
# 知识派生字段（icd10/is_critical/is_antibiotic/antibiotic_level/purpose）、
# 复杂列表（assistants）——LLM 不得发明参数卡结构（plan/04 参数卡唯一契约）。
FIELD_WHITELIST = {
    "patient": ("name", "gender", "age", "department", "bed",
                "admission_date", "discharge_date", "hospital_days"),
    "diagnoses": ("name",),
    "surgeries": ("name", "start_time", "duration_min", "surgeon",
                  "anesthesia", "incision_healing"),
    "medications": ("drug_name", "dose", "dose_unit", "route", "frequency",
                    "start_time", "stop_time"),
    "labs": ("item_name", "value", "value_text", "unit", "abnormal_flag", "report_time"),
    "signatures": ("name", "date"),
    "timeline": ("time",),
}

# 数值叶子的合法性范围（超生理/药理宽口径即丢弃，防幻觉）。
NUMERIC_RANGES = {
    "age": (0.0, 150.0),
    "hospital_days": (0.0, 3650.0),
    "duration_min": (0.0, 1440.0),  # 一台手术不超过一天
    "dose": (0.0, 10000.0),
    "value": (0.0, 2000.0),  # 检验数值宽生理口径（血红蛋白 130、血糖 10 等量级）
}

# 时间叶子必须匹配 "YYYY-MM-DD HH:MM"（生成器唯一时间格式口径）。
TIME_LEAVES = ("admission_date", "discharge_date", "start_time", "stop_time",
               "report_time", "date")
_DT_FULL = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

# 区块 → 默认证据部件（无 evidence 时的定位兜底）。
SECTION_PART = {
    "patient": "入院记录", "diagnoses": "出院记录", "surgeries": "手术记录",
    "medications": "医嘱单", "labs": "检验检查报告",
    "signatures": "出院记录", "timeline": "病程记录",
}

# 候选行关键词（与数字命中共存：含数字或关键词的行才送 LLM）。
FIELD_KEYWORDS = ("患者", "姓名", "性别", "年龄", "科室", "床号", "入院", "出院",
                  "诊断", "手术", "术者", "麻醉", "切口", "医嘱", "用法", "频次",
                  "检验", "检查", "报告", "参考范围", "危急", "签名", "医师",
                  "时间", "检查所见")
_DIGIT_RE = re.compile(r"\d")

SYSTEM_PROMPT = (
    "你是病历参数卡字段抽取助手。只输出一个 JSON 对象，不要输出任何解释文字。"
    "严格遵守：quote 必须是从候选行中逐字复制的连续子串，一字不改；"
    "原文没有的信息一律省略该字段，禁止编造、禁止推测。"
)

_OUTPUT_SPEC = (
    "输出 JSON 格式：\n"
    '{"extractions": [{"field": "<待抽取字段之一>", "source_part": "<该行所属部件名>", '
    '"quote": "<候选行原文的逐字连续子串>", "value": <抽取值>}]}\n'
    "要求：value 是结构化值——数字不带单位，时间用 YYYY-MM-DD HH:MM，文本逐字取自原文；"
    "无把握的字段直接省略，禁止编造。"
)

_FIELD_DESC = {
    "item_name": "检查/检验项目名", "value": "数值结果", "value_text": "文本结果",
    "unit": "单位", "abnormal_flag": "异常标识（↑/↓/正常）",
    "report_time": "报告时间（YYYY-MM-DD HH:MM）", "name": "名称/姓名",
    "age": "年龄（岁，整数）", "gender": "性别", "department": "科室", "bed": "床号",
    "admission_date": "入院时间", "discharge_date": "出院时间",
    "hospital_days": "住院天数（整数）", "dose": "剂量数值", "dose_unit": "剂量单位",
    "route": "给药途径", "frequency": "频次", "drug_name": "药名",
    "start_time": "开始时间", "stop_time": "停止时间", "surgeon": "术者",
    "anesthesia": "麻醉方式", "incision_healing": "切口愈合等级",
    "duration_min": "手术时长（分钟，整数）", "date": "签名日期",
}


@dataclass
class FieldRef:
    """一个待兜底字段的定位：参数卡路径 + 区块 + 叶子 + FieldValue 引用。"""

    path: str  # 如 labs[2].item_name
    section: str
    index: Optional[int]
    leaf: str
    fv: FieldValue


def _threshold() -> float:
    raw = os.getenv(ENV_CONF_THRESHOLD, "")
    try:
        return float(raw) if raw else CONF_THRESHOLD
    except ValueError:
        return CONF_THRESHOLD


def low_confidence_fields(card, threshold: float) -> List[FieldRef]:
    """按白名单收集 confidence < threshold 的字段引用（渲染/解析部件顺序）。"""
    refs: List[FieldRef] = []
    for leaf in FIELD_WHITELIST["patient"]:
        v = getattr(card.patient, leaf, None)
        if isinstance(v, FieldValue) and v.confidence < threshold:
            refs.append(FieldRef("patient.%s" % leaf, "patient", None, leaf, v))
    for section in ("diagnoses", "surgeries", "medications", "labs",
                    "signatures", "timeline"):
        for i, elem in enumerate(getattr(card, section)):
            for leaf in FIELD_WHITELIST[section]:
                v = getattr(elem, leaf, None)
                if isinstance(v, FieldValue) and v.confidence < threshold:
                    refs.append(FieldRef("%s[%d].%s" % (section, i, leaf),
                                         section, i, leaf, v))
    return refs


def candidate_lines(part_texts: Dict[str, str], parts: Optional[Set[str]] = None) -> str:
    """候选行压缩：只保留含数字或领域关键词的行，部件/总量限量（防幻觉三件套之一）。

    part_texts 为空或 parts 过滤后为空 → 返回空串（调用方送全量无意义，应直接降级）。
    """
    chunks: List[str] = []
    total = 0
    for part, text in part_texts.items():  # part_texts 已按部件处理顺序排列
        if parts and part not in parts:
            continue
        kept: List[str] = []
        for ln in text.splitlines():
            ln = ln.rstrip()
            if not ln.strip():
                continue
            if _DIGIT_RE.search(ln) or any(k in ln for k in FIELD_KEYWORDS):
                kept.append(ln)
                if len(kept) >= MAX_LINES_PER_PART:
                    break
        if kept:
            total += len(kept)
            chunks.append("[%s]\n%s" % (part, "\n".join(kept)))
        if total >= MAX_CANDIDATE_LINES:
            chunks.append("（候选行已达上限 %d，其余省略）" % MAX_CANDIDATE_LINES)
            break
    return "\n".join(chunks)


def build_messages(refs: List[FieldRef], candidates_text: str) -> List[dict]:
    """组装抽取对话：系统约束（只输出 JSON + 逐字摘录）+ 字段清单 + 候选行。"""
    field_lines = ["- %s（%s）" % (r.path, _FIELD_DESC.get(r.leaf, r.leaf)) for r in refs]
    user = "待抽取字段（低置信度，需要从候选行中补抽）：\n%s\n\n候选行（[部件名] 行原文）：\n%s\n\n%s" % (
        "\n".join(field_lines), candidates_text, _OUTPUT_SPEC)
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]


_INVALID = object()  # 校验失败哨兵（value 合法地取 None 等值时不与 None 混淆）


def _coerce_value(leaf: str, value: Any):
    """数值叶子做类型与合法性范围校验，时间叶子做格式校验，其余要求非空字符串。

    合法返回规整后的值；不合法返回 _INVALID（调用方按丢弃计数）。
    """
    if leaf in NUMERIC_RANGES:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return _INVALID
        if isinstance(value, str):
            try:
                num = float(value.strip())
            except ValueError:
                return _INVALID
        else:
            num = float(value)
        lo, hi = NUMERIC_RANGES[leaf]
        if not lo <= num <= hi:
            return _INVALID
        return int(num) if num.is_integer() else num
    if not isinstance(value, str) or not value.strip():
        return _INVALID
    value = value.strip()
    if leaf in TIME_LEAVES and not _DT_FULL.fullmatch(value):
        return _INVALID
    return value


def _apply_one(item: Any, refs_by_path: Dict[str, FieldRef],
               part_texts: Dict[str, str], stats: Dict[str, int]) -> None:
    """单条抽取回验 + 写回（就地统计丢弃原因）。"""
    if not isinstance(item, dict):
        stats["n_dropped_other"] += 1
        return
    ref = refs_by_path.get(item.get("field")) if isinstance(item.get("field"), str) else None
    if ref is None:
        stats["n_dropped_other"] += 1  # 未请求的字段：防越权写入参数卡
        return
    source_part = item.get("source_part")
    if not isinstance(source_part, str) or source_part not in part_texts:
        stats["n_dropped_other"] += 1  # 部件不存在
        return
    quote = item.get("quote")
    # 防幻觉核心：quote 必须是该部件原文的逐字连续子串，否则丢弃
    if not isinstance(quote, str) or not quote or quote not in part_texts[source_part]:
        stats["n_dropped_quote"] += 1
        return
    new_value = _coerce_value(ref.leaf, item.get("value"))
    if new_value is _INVALID:
        stats["n_dropped_range"] += 1  # 数值超范围/类型不符/时间格式非法
        return
    ref.fv.value = new_value
    ref.fv.evidence = [Evidence(part=source_part, quote=quote)]
    ref.fv.confidence = EXTRACT_CONFIDENCE
    stats["n_applied"] += 1


def apply_fallback(card, part_texts: Dict[str, str], client: Optional[LLMClient] = None,
                   threshold: Optional[float] = None) -> dict:
    """低置信字段 LLM 兜底（原地写回 card），返回统计 dict。

    - 未配置环境且未显式传 client → available=False（纯规则通路，静默）；
    - 显式传 client 时跳过环境检查（测试注入 mock 用）；
    - 任何失败（LLMError / JSON 损坏 / 结构不合契约 / 意外异常由调用方兜底）
      → 参数卡原样不动，reason 说明，主流程继续纯规则判定。
    """
    threshold = _threshold() if threshold is None else threshold
    stats = {
        "available": True, "reason": "", "n_low_conf": 0, "n_returned": 0,
        "n_applied": 0, "n_dropped_quote": 0, "n_dropped_range": 0, "n_dropped_other": 0,
    }
    if client is None:
        if not llm_available():
            stats["available"] = False
            stats["reason"] = "LLM 未配置（%s/%s/%s）" % (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL)
            return stats
        client = LLMClient()

    refs = low_confidence_fields(card, threshold)
    stats["n_low_conf"] = len(refs)
    if not refs:
        return stats
    refs_by_path = {r.path: r for r in refs}

    parts: Set[str] = set()
    for r in refs:
        parts.add(SECTION_PART.get(r.section, ""))
        parts.update(e.part for e in r.fv.evidence)
    parts.discard("")
    candidates_text = candidate_lines(part_texts, parts)
    messages = build_messages(refs, candidates_text)

    try:
        raw = client.chat(messages, json_mode=True)
    except LLMError as exc:
        stats["reason"] = "LLM 调用失败，降级纯规则通路：%s" % exc
        return stats
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError) as exc:
        stats["reason"] = "LLM 输出 JSON 解析失败，降级纯规则通路：%s" % exc
        return stats
    items = obj.get("extractions") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        stats["reason"] = "LLM 输出不合契约（缺 extractions 数组），降级纯规则通路"
        return stats
    stats["n_returned"] = len(items)
    for item in items:
        _apply_one(item, refs_by_path, part_texts, stats)
    return stats
