"""知识库构建工具：raw 规范原文 → blocks 条文块 → rules 规则表（M3）。

数据派生链：条文块引文从 raw/*.txt 程序化摘取（保证逐字，杜绝转写笔误）；
规则 basis 引文按（文号, 条款）从已建 blocks 取同一文本（单一来源）。
重跑本脚本应零 diff（确定性抽取，无随机）。产出：
  data/knowledge/blocks/*.json（每份规范一个文件）
  data/knowledge/rules/formal_rules.json / integrity_rules.json

运行：py -X utf8 tools/build_knowledge.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "knowledge" / "raw"
BLOCKS = ROOT / "data" / "knowledge" / "blocks"
RULES = ROOT / "data" / "knowledge" / "rules"

sys.path.insert(0, str(ROOT / "src"))


# ---------------------------------------------------------------- 抽取原语

def _read(name: str) -> str:
    return (RAW / name).read_text(encoding="utf-8")


def between(text: str, start: str, end: str) -> str:
    """摘取 start 锚点起、end 锚点前的一段（strip 后仍为原文逐字子串）。"""
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j].strip()


def line_span(text: str, start_with: str, end_with: str, after: str = "") -> str:
    """按行摘取：after 行之后、start_with 行起，到 end_with 行前（不含）。

    用于 PDF 文本层（病案质控指标）：定义跨物理行，锚定"指标N"行后取
    "定义："起、"计算公式"前，避开页码残留与分式错位的公式区。
    """
    lines = text.splitlines()
    begin = 0
    if after:
        begin = next(i for i, ln in enumerate(lines) if ln.strip().startswith(after))
    i = next(i for i in range(begin, len(lines)) if lines[i].strip().startswith(start_with))
    j = next(i for i in range(i + 1, len(lines)) if lines[i].strip().startswith(end_with))
    return "\n".join(lines[i:j]).strip()


# ---------------------------------------------------------------- blocks 定义

# (block_id 前缀, 文件名, document, document_no, [(clause, quote), ...])
_BW = "病历书写基本规范_卫医政发2010-11号.txt"
_HX = "医疗质量安全核心制度要点_国卫医发2018-8号.txt"
_GL = "医疗机构病历管理规定2013年版_国卫医发2013-31号.txt"
_ZB = "病案管理质量控制指标2021年版_文本层.txt"
_SY = "住院病案首页数据填写质量规范暂行_国卫办医发2016-24号.txt"

DOCS = (
    ("BW2010", _BW, "病历书写基本规范", "卫医政发〔2010〕11号", lambda t: (
        ("第三条", between(t, "第三条", "第四条")),
        ("第八条", between(t, "第八条", "第九条")),
        ("第九条", between(t, "第九条", "第十条")),
        ("第十七条", between(t, "第十七条", "第十八条")),
        ("第十八条（二）", between(t, "（二）主诉", "（三）现病史")),
        ("第十八条（三）", between(t, "（三）现病史", "（四）既往史")),
        ("第十八条（九）", between(t, "（九）初步诊断", "（十）书写")),
        ("第十八条（十）", between(t, "（十）书写", "第十九条")),
        ("第十八条（十二）", between(t, "（十二）术前讨论记录", "（十三）麻醉术前访视记录")),
        ("第十八条（十五）", between(t, "（十五）手术记录", "（十六）手术安全核查记录")),
        ("第十八条（十八）", between(t, "（十八）术后首次病程记录", "（十九）麻醉术后访视记录")),
        ("第十八条（二十）", between(t, "（二十）出院记录", "（二十一）死亡记录")),
        ("第二十二条", between(t, "第二十二条", "病程记录的要求及内容")),
        ("第二十二条（一）", between(t, "（一）首次病程记录", "（二）日常病程记录")),
        ("第二十八条", between(t, "第二十八条", "第二十九条")),
        ("第二十九条", between(t, "第二十九条", "第三十条")),
    )),
    ("HX2018", _HX, "医疗质量安全核心制度要点", "国卫医发〔2018〕8号", lambda t: (
        ("八、术前讨论制度（定义）", between(t, "指以降低手术风险、保障手术安全为目的", "（二）基本要求")),
        ("八-3", _line(t, "3.术前讨论完成后")),
        ("十四、危急值报告制度（定义）", between(t, "指对提示患者处于生命危急状态的检查、检验结果", "（二）基本要求")),
        ("十四-1", _line(t, "1.医疗机构应当分别建立住院和门急诊患者危急值报告具体管理流程")),
        ("十四-5", _line(t, "5.临床科室任何接收到危急值信息的人员")),
        ("十五-2", _line(t, "2.医疗机构病历书写应当做到客观、真实、准确、及时、完整、规范")),
        ("十六-1", _line(t, "1.根据抗菌药物的安全性、疗效、细菌耐药性和价格等因素")),
        ("十六-3", _line(t, "3.医疗机构应当建立全院特殊使用级抗菌药物会诊专家库")),
        ("十七-2", _line(t, "2.临床用血审核包括但不限于用血申请")),
    )),
    ("GL2013", _GL, "医疗机构病历管理规定（2013年版）", "国卫医发〔2013〕31号", lambda t: (
        ("第八条", between(t, "第八条", "第九条")),
        ("第十四条", between(t, "第十四条", "第十五条")),
        ("第二十九条", between(t, "第二十九条", "第三十条")),
    )),
    ("ZB2021", _ZB, "病案管理质量控制指标（2021年版）", "国卫办医函〔2021〕28号", lambda t: (
        ("指标四（MER-TL-01）", line_span(t, "定义：单位时间内，入院记录", "计算公式", after="指标四")),
        ("指标五（MER-TL-02）", line_span(t, "定义：单位时间内，手术记录", "计算公式", after="指标五")),
        ("指标六（MER-TL-03）", line_span(t, "定义：单位时间内，出院记录", "计算公式", after="指标六")),
        ("指标七（MER-TL-04）", line_span(t, "定义：单位时间内，病案首页", "计算公式", after="指标七")),
        ("指标十一（MER-D&T-01）", line_span(t, "定义：单位时间内，抗菌药物使用", "计算公式", after="指标十一")),
        ("指标十四（MER-D&T-04）", line_span(t, "定义：单位时间内，手术相关记录完整", "计算公式", after="指标十四")),
        ("指标十六（MER-D&T-06）", line_span(t, "定义：单位时间内，临床用血相关记录符合", "计算公式", after="指标十六")),
        ("指标二十一（MER-TQ-03）", line_span(t, "定义：单位时间内，病案首页中主要诊断填写正确", "计算公式", after="指标二十一")),
        ("指标二十六（MER-TQ-08）", line_span(t, "定义：单位时间内，规范签署知情同意书", "计算公式", after="指标二十六")),
    )),
    ("SY2016", _SY, "住院病案首页数据填写质量规范（暂行）", "国卫办医发〔2016〕24号", lambda t: (
        ("第三条", between(t, "第三条", "第四条")),
        ("第五条", between(t, "第五条", "第六条")),
        ("第六条", between(t, "第六条", "第七条")),
        ("第八条", between(t, "第八条", "第九条")),
        ("第十条", between(t, "第十条", "第十一条")),
    )),
)


def _line(text: str, prefix: str) -> str:
    """取 prefix 开头的整行（strip），用于核心制度要点的单条基本要求行。"""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(prefix):
            return s
    raise LookupError("未找到行：%s" % prefix)


def build_blocks() -> dict:
    """{文号: (clause → quote)}，并落盘 blocks/*.json。"""
    BLOCKS.mkdir(parents=True, exist_ok=True)
    index = {}
    for prefix, fname, document, doc_no, extract in DOCS:
        text = _read(fname)
        items = extract(text)
        for clause, quote in items:
            if quote not in text:
                raise AssertionError("引文非原文子串：%s %s" % (doc_no, clause))
        index[doc_no] = dict(items)
        payload = {
            "document": document,
            "document_no": doc_no,
            "source_file": "raw/" + fname,
            "blocks": [
                {"block_id": "%s-%s" % (prefix, clause), "clause": clause, "quote": quote}
                for clause, quote in items
            ],
        }
        out = BLOCKS / ("%s.json" % document)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[blocks] %-24s %2d 块" % (out.name, len(items)))
    return index


# ---------------------------------------------------------------- rules 定义

def _basis(index, doc_no, clause, status="已核对"):
    quote = index[doc_no][clause]
    document = next(d[2] for d in DOCS if d[3] == doc_no)
    return {"document": document, "document_no": doc_no, "clause": clause,
            "quote": quote, "status": status}


BW, HX, SY = "卫医政发〔2010〕11号", "国卫医发〔2018〕8号", "国卫办医发〔2016〕24号"


def _rule(rid, name, rtype, severity, channel, basis, params,
          suggestion="", only_if=None):
    return {"id": rid, "name": name, "type": rtype, "severity": severity,
            "channel": channel, "basis": basis,
            "only_if": only_if or {}, "params": params,
            "suggestion_template": suggestion}


def build_rules(index) -> None:
    formal = [
        # ---- required_field（数据源：parse_warnings 区块存在性，plan/06 定稿口径）
        _rule("F-REQ-01", "入院记录缺主诉", "required_field", "HIGH", "formal",
              _basis(index, BW, "第十八条（二）"),
              {"part": "入院记录", "block": "主诉"},
              "入院记录缺少主诉，请按规范补写主诉（主要症状/体征及持续时间）。"),
        _rule("R-REQ-02", "入院记录缺现病史", "required_field", "MEDIUM", "formal",
              _basis(index, BW, "第十八条（三）"),
              {"part": "入院记录", "block": "现病史"},
              "入院记录缺少现病史，请按规范补写。"),
        _rule("R-REQ-03", "入院记录缺入院诊断", "required_field", "HIGH", "formal",
              _basis(index, BW, "第十八条（九）"),
              {"part": "入院记录", "block": "入院诊断"},
              "入院记录缺少入院诊断（初步诊断），请补写并做到主次分明。"),
        _rule("R-REQ-04", "出院记录缺出院诊断", "required_field", "HIGH", "formal",
              _basis(index, BW, "第十八条（二十）"),
              {"part": "出院记录", "block": "出院诊断"},
              "出院记录缺少出院诊断，请补写。"),
        _rule("R-REQ-05", "出院记录缺诊疗经过/出院情况/出院医嘱", "required_field", "MEDIUM", "formal",
              _basis(index, BW, "第十八条（二十）"),
              {"part": "出院记录", "blocks": ["诊疗经过", "出院情况", "出院医嘱"]},
              "出院记录缺少必备段落：{missing}，请按规范补齐。"),
        _rule("R-REQ-06", "手术病种缺手术记录", "required_field", "HIGH", "formal",
              _basis(index, BW, "第十八条（十五）"),
              {"require": "surgery_record"},
              "出院诊疗经过提及手术但病历中无手术记录部件，请补写手术记录。"),
        # ---- timeliness
        _rule("F-TIME-01", "入院记录未在入院后24小时内完成", "timeliness", "HIGH", "formal",
              _basis(index, BW, "第十七条"),
              {"event": "入院记录完成", "anchor_event": "入院", "limit_hours": 24},
              "入院记录完成于入院后 {actual_hours} 小时，超出 24 小时时限，请核查书写时效。"),
        _rule("F-TIME-02", "首次病程记录未在入院后8小时内完成", "timeliness", "HIGH", "formal",
              _basis(index, BW, "第二十二条（一）"),
              {"event": "首次病程记录", "anchor_event": "入院", "limit_hours": 8},
              "首次病程记录完成于入院后 {actual_hours} 小时，超出 8 小时时限，请核查书写时效。"),
        _rule("F-TIME-03", "术后首次病程记录未即时完成", "timeliness", "NEED_CONFIRM", "formal",
              _basis(index, BW, "第十八条（十八）", status="待核对"),
              {"event": "术后首次病程", "anchor": "surgery_end", "limit_hours": 2},
              "术后首次病程记录完成于手术结束后 {actual_hours} 小时；规范要求“即时完成”，"
              "数值化时限（当前阈值 2 小时）待核对，请人工确认。",
              only_if={"any_keyword": ["术后首次病程记录"]}),
        # ---- signature_format
        _rule("F-SIGN-01", "缺术者或上级审签签名", "signature_format", "HIGH", "formal",
              _basis(index, BW, "第八条"),
              {"check": "required_signatures",
               "items": [{"role": "术者", "when_surgery": True},
                          {"role": "主治医师", "require_part": "出院记录"}]},
              "缺少{roles}签名，请按规定由相应医务人员签名。"),
        _rule("R-SIGN-02", "签名缺日期", "signature_format", "LOW", "formal",
              _basis(index, BW, "第九条"),
              {"check": "signature_date_present"},
              "{roles}签名未注明日期，请补签日期（24 小时制）。"),
        _rule("R-SIGN-03", "入院记录缺住院医师签名", "signature_format", "MEDIUM", "formal",
              _basis(index, BW, "第十八条（十）"),
              {"check": "role_present", "role": "住院医师", "require_part": "入院记录"},
              "入院记录缺住院医师（记录者）签名，请补签。"),
    ]
    integrity = [
        # ---- cross_consistency
        _rule("C-DIAG-01", "感染性出院诊断缺抗菌用药医嘱", "cross_consistency", "HIGH", "integrity",
              _basis(index, SY, "第五条"),
              {"compare": "diagnosis_medication",
               "diagnosis_keywords": ["肺炎", "肺部感染"], "require_drug": "antibiotic"},
              "出院诊断“{diag}”全程无抗菌药物医嘱，诊断依据不可追溯，请核对医嘱或补充诊断依据。"),
        _rule("C-SURG-01", "手术记录术式与术前讨论不一致", "cross_consistency", "HIGH", "integrity",
              _basis(index, BW, "第三条"),
              {"compare": "surgery_name_vs_preop"},
              "手术记录术式“{performed}”与术前讨论拟施术式“{planned}”不一致，请核对。",
              only_if={"any_keyword": ["手术记录"]}),
        _rule("C-SURG-02", "手术记录术者与术者签名不一致", "cross_consistency", "HIGH", "integrity",
              _basis(index, BW, "第八条"),
              {"compare": "surgeon_vs_operator_signature"},
              "手术记录术者“{surgeon}”与术者签名“{signed}”不一致，请核对。",
              only_if={"any_keyword": ["手术记录"]}),
        _rule("C-ORD-01", "医嘱停止时间晚于出院时间", "cross_consistency", "HIGH", "integrity",
              _basis(index, BW, "第二十八条"),
              {"compare": "med_stop_vs_discharge"},
              "医嘱“{drug}”停止时间（{stop}）晚于出院时间（{discharge}），请核对医嘱时限。"),
        _rule("R-X-05", "出院记录入院时间与入院记录不一致", "cross_consistency", "MEDIUM", "integrity",
              _basis(index, SY, "第八条"),
              {"compare": "admission_date_across_parts"},
              "出院记录入院时间（{in_discharge}）与入院记录（{in_admission}）不一致，请核对。"),
        _rule("R-X-06", "住院天数与出入院日期不符", "cross_consistency", "MEDIUM", "integrity",
              _basis(index, SY, "第三条"),
              {"compare": "hospital_days_vs_dates"},
              "住院天数填写 {days} 天，按出入院日期计算应为 {computed} 天，请核对。"),
        _rule("R-X-07", "手术记录术后诊断与出院诊断不一致", "cross_consistency", "MEDIUM", "integrity",
              _basis(index, SY, "第五条"),
              {"compare": "postop_dx_vs_discharge_dx"},
              "术后诊断“{postop}”与出院诊断“{discharge}”不一致，可能为补充诊断或笔误，请人工确认。"),
        # ---- medication_logic
        _rule("C-ANTI-01", "特殊使用级抗菌药无审批记录", "medication_logic", "CRITICAL", "integrity",
              _basis(index, HX, "十六-3"),
              {"check": "special_antibiotic_approval", "level": "特殊使用级",
               "approval_keywords": ["会诊", "审批", "核准"]},
              "使用特殊使用级抗菌药物“{drug}”，病程中未见会诊/审批记录，请核查分级管理流程。"),
        _rule("C-BLOOD-01", "术中用血无用血审批病程记录", "medication_logic", "HIGH", "integrity",
              _basis(index, HX, "十七-2"),
              {"check": "blood_approval"},
              "术中输注{drug}但病程中无用血审批记录，请核查临床用血审核流程。"),
        _rule("R-MED-03", "长期医嘱缺剂量或频次", "medication_logic", "MEDIUM", "integrity",
              _basis(index, BW, "第二十八条"),
              {"check": "order_completeness", "scope": "longterm",
               "fields": ["dose", "frequency"]},
              "长期医嘱“{drug}”缺少{missing}，医嘱内容应准确、清楚，请补全。"),
        _rule("R-MED-04", "抗菌药物医嘱未标注分级", "medication_logic", "MEDIUM", "integrity",
              _basis(index, HX, "十六-1"),
              {"check": "antibiotic_level_present"},
              "抗菌药物“{drug}”未标注分级（非限制/限制/特殊使用级），请补标。"),
        _rule("R-MED-05", "临时医嘱缺开始时间", "medication_logic", "LOW", "integrity",
              _basis(index, BW, "第二十八条"),
              {"check": "order_completeness", "scope": "temporary",
               "fields": ["start_time"]},
              "临时医嘱“{drug}”缺少开始时间，医嘱应注明下达时间并具体到分钟，请补全。"),
        # ---- lab_logic
        _rule("C-LAB-01", "危急值无病程处置记录", "lab_logic", "HIGH", "integrity",
              _basis(index, HX, "十四-5"),
              {"check": "critical_closed_loop", "handling_marker": "危急值处置"},
              "检验项“{item}”出现危急值（{value} {unit}），病程中未见危急值处置记录，请核查报告闭环。"),
        _rule("C-LAB-02", "危急值血红蛋白无处置且诊断未体现", "lab_logic", "HIGH", "integrity",
              _basis(index, HX, "十四-5"),
              {"check": "critical_item_unaddressed", "item": "血红蛋白",
               "diagnosis_keywords": ["贫血"]},
              "血红蛋白危急值（{value} {unit}）无病程处置记录，且诊断未体现相关情况，请核查。"),
        _rule("R-LAB-03", "检验条目缺报告时间", "lab_logic", "MEDIUM", "integrity",
              _basis(index, BW, "第二十九条"),
              {"check": "report_time_present"},
              "检验条目“{item}”缺报告时间，请补全。"),
        # ---- timeline_logic
        _rule("C-TIME-01", "出院时间早于手术时间", "timeline_logic", "CRITICAL", "integrity",
              _basis(index, SY, "第八条"),
              {"check": "discharge_after_surgery"},
              "出院时间（{discharge}）早于手术开始时间（{surgery}），时间轴矛盾，请核对。"),
        _rule("R-TL-04", "手术开始时间早于入院时间", "timeline_logic", "CRITICAL", "integrity",
              _basis(index, SY, "第八条"),
              {"check": "surgery_after_admission"},
              "手术开始时间（{surgery}）早于入院时间（{admission}），时间轴矛盾，请核对。",
              only_if={"any_keyword": ["手术记录"]}),
        _rule("R-TL-05", "术前讨论晚于手术开始", "timeline_logic", "HIGH", "integrity",
              _basis(index, HX, "八-3"),
              {"check": "preop_before_surgery"},
              "术前讨论时间（{preop}）晚于手术开始时间（{surgery}），术前讨论应先于手术，请核对。",
              only_if={"any_keyword": ["手术记录"]}),
        _rule("R-TL-06", "首次病程记录早于入院时间", "timeline_logic", "HIGH", "integrity",
              _basis(index, BW, "第二十二条"),
              {"check": "first_course_after_admission"},
              "首次病程记录时间（{first_course}）早于入院时间（{admission}），时间轴矛盾，请核对。"),
        _rule("R-TL-07", "入院记录记录时间早于入院时间", "timeline_logic", "MEDIUM", "integrity",
              _basis(index, BW, "第十七条"),
              {"check": "record_time_after_admission"},
              "入院记录记录时间（{record_time}）早于入院时间（{admission}），时间轴矛盾，请核对。"),
        _rule("R-TL-08", "危急值处置记录早于检验报告时间", "timeline_logic", "MEDIUM", "integrity",
              _basis(index, HX, "十四-1"),
              {"check": "critical_handling_after_report"},
              "危急值处置时间（{handling}）早于检验报告时间（{report}），时间轴矛盾，请核对。"),
    ]
    RULES.mkdir(parents=True, exist_ok=True)
    for fname, channel, items in (
            ("formal_rules.json", "formal", formal),
            ("integrity_rules.json", "integrity", integrity)):
        payload = {"channel": channel, "description": "M3 规则表（%s通道）；schema 见 plan/04 §3，由 tools/build_knowledge.py 生成" % channel,
                   "rules": items}
        out = RULES / fname
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("[rules] %-24s %2d 条" % (out.name, len(items)))


def main() -> int:
    index = build_blocks()
    build_rules(index)
    total = sum(len(v) for v in index.values())
    print("知识库构建完成：blocks %d 块 / rules %d 条" % (total, 12 + 21))
    return 0


if __name__ == "__main__":
    sys.exit(main())
