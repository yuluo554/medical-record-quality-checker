"""truth.json 对账：生成器真值 ↔ RecordCard 往返校验 + 证据子串校验 + 数据集盘点。

M1 DoD 的验收路径：对 data/samples、data/paired 全量跑 verify_dataset，
任何记录的问题（往返不一致 / 证据不是原文子串 / 住院天数不一致）都会被列出。
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from ..models import FieldValue, RecordCard
from ..parsers.base import detect_part
from .inject import INJECTION_ORDER

__all__ = ["iter_field_values", "verify_record_dir", "verify_dataset"]

_DATE_FMT = "%Y-%m-%d %H:%M"


def iter_field_values(card: RecordCard) -> Iterator[Tuple[str, FieldValue]]:
    """遍历参数卡全部 FieldValue（含列表内嵌套），产出 (字段路径, 字段)。"""
    for name in ("name", "gender", "age", "department", "bed", "admission_date", "discharge_date", "hospital_days"):
        fv = getattr(card.patient, name)
        if fv is not None:
            yield "patient.%s" % name, fv
    for i, d in enumerate(card.diagnoses):
        for name in ("name", "icd10"):
            if getattr(d, name) is not None:
                yield "diagnoses[%d].%s" % (i, name), getattr(d, name)
    for i, s in enumerate(card.surgeries):
        for name in ("name", "start_time", "duration_min", "surgeon", "anesthesia", "incision_healing"):
            if getattr(s, name) is not None:
                yield "surgeries[%d].%s" % (i, name), getattr(s, name)
        for j, a in enumerate(s.assistants):
            yield "surgeries[%d].assistants[%d]" % (i, j), a
    for i, m in enumerate(card.medications):
        for name in ("drug_name", "dose", "dose_unit", "route", "frequency", "start_time",
                     "stop_time", "is_antibiotic", "antibiotic_level", "purpose"):
            if getattr(m, name) is not None:
                yield "medications[%d].%s" % (i, name), getattr(m, name)
    for i, lab in enumerate(card.labs):
        for name in ("item_name", "value", "value_text", "unit", "abnormal_flag",
                     "is_critical", "report_time"):
            if getattr(lab, name) is not None:
                yield "labs[%d].%s" % (i, name), getattr(lab, name)
    for i, ev in enumerate(card.timeline):
        if ev.time is not None:
            yield "timeline[%d].time" % i, ev.time
    for i, sig in enumerate(card.signatures):
        for name in ("name", "date"):
            if getattr(sig, name) is not None:
                yield "signatures[%d].%s" % (i, name), getattr(sig, name)


def _load_parts(record_dir: Path) -> Tuple[Dict[str, str], List[str]]:
    """读部件文本，按内容标题识别归属；返回 (部件映射, 未能识别的文件)。"""
    parts: Dict[str, str] = {}
    unknown: List[str] = []
    for path in sorted(record_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        part = detect_part(text)
        if part is None:
            unknown.append(path.name)
        else:
            parts[part] = text
    return parts, unknown


def verify_record_dir(record_dir: Path, expect_defects: bool = False) -> List[str]:
    """单份记录对账，返回问题列表（空 = 通过）。"""
    problems: List[str] = []
    truth_path = record_dir / "truth.json"
    if not truth_path.is_file():
        return ["%s: 缺少 truth.json" % record_dir.name]
    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    # 1) 参数卡往返：truth → RecordCard → dict 与原值全等
    card = RecordCard.from_dict(truth)
    if json.dumps(card.to_dict(), ensure_ascii=False, sort_keys=True) != \
            json.dumps(truth, ensure_ascii=False, sort_keys=True):
        problems.append("%s: truth.json 与 RecordCard 往返不一致" % record_dir.name)

    # 2) 证据子串：每条 Evidence.quote 必须是对应部件原文的逐字子串
    parts, unknown = _load_parts(record_dir)
    if unknown:
        problems.append("%s: 部件未识别 %s" % (record_dir.name, unknown))
    for part, text in parts.items():
        if "{" in text and "}" in text:
            problems.append("%s: %s 疑似残留模板占位符（{...}）" % (record_dir.name, part))
    for path_, fv in iter_field_values(card):
        for ev in fv.evidence:
            if not ev.quote:
                problems.append("%s: %s 证据摘录为空" % (record_dir.name, path_))
            elif ev.part not in parts:
                problems.append("%s: %s 证据部件不存在：%s" % (record_dir.name, path_, ev.part))
            elif ev.quote not in parts[ev.part]:
                problems.append("%s: %s 证据摘录不是 %s 原文子串：%r"
                                % (record_dir.name, path_, ev.part, ev.quote[:40]))

    # 3) 日期与住院天数一致性
    adm = card.patient.admission_date.value if card.patient.admission_date else None
    dis = card.patient.discharge_date.value if card.patient.discharge_date else None
    days = card.patient.hospital_days.value if card.patient.hospital_days else None
    try:
        from datetime import datetime
        a = datetime.strptime(adm, _DATE_FMT)
        d = datetime.strptime(dis, _DATE_FMT)
        if d < a:
            problems.append("%s: 出院时间早于入院时间" % record_dir.name)
        if days != (d.date() - a.date()).days:
            problems.append("%s: 住院天数 %r 与日期差 %d 不一致"
                            % (record_dir.name, days, (d.date() - a.date()).days))
        for i, ev in enumerate(card.timeline):
            if ev.event in ("入院", "出院") and ev.time is not None:
                want = adm if ev.event == "入院" else dis
                if ev.time.value != want:
                    problems.append("%s: timeline[%d] %s 时间与患者信息不一致"
                                    % (record_dir.name, i, ev.event))
    except (TypeError, ValueError) as exc:
        problems.append("%s: 日期解析失败 %s" % (record_dir.name, exc))

    # 4) paired 集：defects.json 结构与缺陷 ID 合法性
    defects_path = record_dir / "defects.json"
    if defects_path.is_file() or expect_defects:
        if not defects_path.is_file():
            problems.append("%s: 配对集缺少 defects.json" % record_dir.name)
        else:
            with open(defects_path, "r", encoding="utf-8") as f:
                defects = json.load(f)
            for item in defects.get("defects", []):
                if item.get("defect_id") not in INJECTION_ORDER:
                    problems.append("%s: defects.json 出现对照表之外的缺陷 ID：%r"
                                    % (record_dir.name, item.get("defect_id")))
    return problems


def verify_dataset(dataset_dir: Path) -> Dict[str, Any]:
    """对一个数据集目录全量对账，返回汇总（含按缺陷 ID 的配额盘点）。"""
    record_dirs = sorted(d for d in dataset_dir.iterdir() if d.is_dir()) \
        if dataset_dir.is_dir() else []
    problems: List[str] = []
    defect_counts: Dict[str, int] = {did: 0 for did in INJECTION_ORDER}
    clean = 0
    for rd in record_dirs:
        probs = verify_record_dir(rd)
        problems.extend(probs)
        dp = rd / "defects.json"
        if dp.is_file():
            with open(dp, "r", encoding="utf-8") as f:
                defects = json.load(f)
            items = defects.get("defects", [])
            if not items:
                clean += 1
            for item in items:
                did = item.get("defect_id")
                if did in defect_counts:
                    defect_counts[did] += 1
    return {
        "dataset": str(dataset_dir),
        "records": len(record_dirs),
        "clean": clean,
        "defect_counts": {k: v for k, v in defect_counts.items() if v},
        "problems": problems,
    }
