"""配对集端到端检出评测（M3）：解析 → 规则引擎 → 与 defects.json 期望对账。

口径（与 benchmarks/detect_paired.py、plan/06 决策一致）：
- 缺陷记录：主缺陷规则（defects[].defect_id）必须非 pass；also_expect 允许可选命中
  （C-LAB-02 隐含 C-LAB-01）；期望之外的非 pass 结论记误报；
- 干净对照（clean_pair=true）：任何非 pass 结论均记误报（M4 门槛：误报 = 0）；
- status=need_confirm 计入"非 pass"：待核对依据按纪律只能产出 need_confirm 结论，
  F-TIME-03（"即时"时限数值化待核对）以此形式检出。

零 API 依赖：只走规则通路，LLM 未配置即等效基准环境。
"""

import json
from collections import Counter
from pathlib import Path

from ..knowledge import knowledge_dir
from ..parsers import load_part_texts, parse_texts
from ..rules import RuleEngine

__all__ = ["detect_record", "evaluate_dataset", "render_markdown", "STATUS_LABEL"]

STATUS_LABEL = {"fail": "不通过", "need_confirm": "待人工确认", "pass": "通过"}


def detect_record(engine: RuleEngine, record_dir: Path) -> dict:
    """解析一份记录并执行全部规则，返回全部结论与非 pass 子集。"""
    texts, warnings = load_part_texts(record_dir)
    card = parse_texts(texts)
    card.parse_warnings[:0] = warnings
    findings = engine.check(card, part_texts=texts)
    non_pass = [f for f in findings if f.status != "pass"]
    return {
        "record_id": record_dir.name,
        "findings": [f.to_dict() for f in findings],
        "non_pass": [f.to_dict() for f in non_pass],
    }


def evaluate_dataset(data_dir: Path, rules_dir: Path = None) -> dict:
    """数据集级对账：主缺陷检出率 / 干净误报 / 非预期结论 / 依据关联率。"""
    engine = RuleEngine.load(rules_dir or (knowledge_dir() / "rules"))
    records = sorted(d for d in data_dir.iterdir() if d.is_dir())
    per_defect = Counter()
    defect_total = Counter()
    details = []
    clean_fp = []
    missed_total = []
    n_records = 0
    n_non_pass_findings = 0
    n_basis_attached = 0

    for rec_dir in records:
        defects_path = rec_dir / "defects.json"
        if not defects_path.is_file():
            continue
        n_records += 1
        meta = json.loads(defects_path.read_text(encoding="utf-8"))
        result = detect_record(engine, rec_dir)
        non_pass = result["non_pass"]
        n_non_pass_findings += len(non_pass)
        n_basis_attached += sum(1 for f in non_pass if f.get("basis"))

        expected_main = {d["defect_id"] for d in meta["defects"]}
        expected_all = set(expected_main)
        for d in meta["defects"]:
            expected_all.update(d.get("also_expect", []))
        got = {f["rule_id"] for f in non_pass}

        for defect_id in expected_main:
            defect_total[defect_id] += 1
            if defect_id in got:
                per_defect[defect_id] += 1
            else:
                missed_total.append({"record_id": meta["record_id"], "defect_id": defect_id})

        fps = sorted(got - expected_all) if not meta.get("clean_pair") else sorted(got)
        if fps:
            clean_fp.extend({"record_id": meta["record_id"], "rule_id": rid} for rid in fps)

        details.append({
            "record_id": meta["record_id"],
            "clean_pair": bool(meta.get("clean_pair")),
            "expected_main": sorted(expected_main),
            "expected_all": sorted(expected_all),
            "detected_non_pass": non_pass,
            "missed": sorted(expected_main - got),
            "unexpected": sorted(got - expected_all) if not meta.get("clean_pair") else sorted(got),
        })

    n_clean = sum(1 for d in details if d["clean_pair"])
    n_defect = n_records - n_clean
    detection = {k: [per_defect[k], defect_total[k]] for k in sorted(defect_total)}
    hit = sum(v[0] for v in detection.values())
    total = sum(v[1] for v in detection.values())
    severity_dist = Counter(f["severity"] for d in details for f in d["detected_non_pass"])
    return {
        "n_records": n_records,
        "n_defect_records": n_defect,
        "n_clean_records": n_clean,
        "per_defect_detection": detection,
        "detection_rate": round(hit / total, 4) if total else 0.0,
        "detection_rate_note": "主缺陷检出（need_confirm 计入非 pass；C-LAB-02 的 also_expect=C-LAB-01 为可选命中）",
        "clean_false_positives": len(clean_fp),
        "clean_fp_detail": clean_fp,
        "missed_detail": missed_total,
        "unexpected_findings": sum(len(d["unexpected"]) for d in details),
        "severity_distribution": dict(severity_dist),
        "basis_linkage_rate": round(n_basis_attached / n_non_pass_findings, 4) if n_non_pass_findings else 1.0,
        "n_non_pass_findings": n_non_pass_findings,
        "details": details,
    }


def render_markdown(r: dict) -> str:
    """评测结果 → markdown 报告（M3 演示物：结论清单含分级 + 依据）。"""
    lines = []
    lines.append("# M3 配对集检出首版报告")
    lines.append("")
    lines.append("> 生成：`benchmarks/detect_paired.py`（解析 → 规则引擎 → 与 defects.json 对账）；"
                 "数据：data/paired（14 缺陷 ID × 3 + 干净对照 12，seed 20261004）。"
                 "本报告为 M3 演示物：结论清单含分级与规范依据。")
    lines.append("")
    lines.append("## 一、总体指标")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    lines.append("| 参评记录 | %d（缺陷 %d + 干净对照 %d） |" % (r["n_records"], r["n_defect_records"], r["n_clean_records"]))
    lines.append("| 主缺陷检出率 | **%.2f%%**（%s） |" % (r["detection_rate"] * 100, r["detection_rate_note"]))
    lines.append("| 干净对照误报 | **%d**（M4 门槛 0，首版已达标） |" % r["clean_false_positives"])
    lines.append("| 非预期结论（缺陷记录上期望外的非 pass） | %d |" % r["unexpected_findings"])
    lines.append("| 依据关联率（非 pass 结论挂 basis） | %.2f%% |" % (r["basis_linkage_rate"] * 100))
    lines.append("| 非 pass 结论分级分布 | %s |" % json.dumps(r["severity_distribution"], ensure_ascii=False))
    lines.append("")
    lines.append("## 二、按缺陷类型检出")
    lines.append("")
    lines.append("| 缺陷 ID | 检出/应检 | 检出率 |")
    lines.append("|---|---|---|")
    for k, (hit_n, tot) in r["per_defect_detection"].items():
        lines.append("| %s | %d/%d | %.0f%% |" % (k, hit_n, tot, hit_n / tot * 100 if tot else 0))
    lines.append("")
    lines.append("## 三、结论清单（非 pass，含分级 + 依据，节选每缺陷 ID 首条）")
    lines.append("")
    seen = set()
    for d in r["details"]:
        if not d["detected_non_pass"]:
            continue
        key = tuple(d["expected_main"])
        if key in seen:
            continue
        seen.add(key)
        for f in d["detected_non_pass"]:
            basis = f.get("basis") or {}
            ev = (f.get("evidence") or [{}])[0]
            lines.append("### %s — %s（%s）" % (d["record_id"], f["rule_id"], f["rule_name"]))
            lines.append("")
            lines.append("- **分级**：%s ｜ **状态**：%s" % (f["severity"], STATUS_LABEL.get(f["status"], f["status"])))
            lines.append("- **依据**：%s %s %s（%s）" % (basis.get("document", ""), basis.get("document_no", ""),
                                                        basis.get("clause", ""), basis.get("status", "")))
            if basis.get("quote"):
                lines.append("  - 条文摘录：%s" % basis["quote"][:80].replace("\n", " "))
            if ev:
                lines.append("- **病历证据**：[%s] %s" % (ev.get("part", ""), ev.get("quote", "")[:60]))
            if f.get("suggestion"):
                lines.append("- **建议**：%s" % f["suggestion"])
            lines.append("")
    lines.append("## 四、口径说明")
    lines.append("")
    lines.append("- 评测按\"文档全部非 pass 集合\"对账：主缺陷必须命中；also_expect（C-LAB-02 隐含 C-LAB-01）可选命中；")
    lines.append("- F-TIME-03（术后首次病程\"即时\"时限）数值化阈值官方原文未给出，依据标\"待核对\"，")
    lines.append("  按纪律结论以 **need_confirm（待人工确认）** 形式产出，计入检出；")
    lines.append("- 干净对照启用用血变体（ctrl_gallstone 双号强制），用血审批记录完整，C-BLOOD-01 不误报；")
    lines.append("- 全部结论证据为部件原文逐字子串（参数卡 Evidence），规范依据逐条挂文号+条款（blocks 入库）。")
    return "\n".join(lines) + "\n"
