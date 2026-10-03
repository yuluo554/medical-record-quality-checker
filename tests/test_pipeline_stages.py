"""端到端流水线节点测试：五节点组装、汇总口径、失败即停、docx 导出节点。"""

import json
from pathlib import Path

import pytest

from mrqc.pipeline import CTX_CARD, CTX_FINDINGS, CTX_SUMMARY, CTX_TIMINGS
from mrqc.pipeline.stages import build_pipeline, summarize
from mrqc.rules.finding import Basis, Finding, Severity

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD = REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01"


def _finding(rule_id="F-X", status="fail", severity=Severity.HIGH, with_basis=True):
    return Finding(rule_id=rule_id, rule_name="测试规则", severity=severity,
                   basis=Basis(document="规范", document_no="文号", clause="第一条",
                               quote="引文") if with_basis else None,
                   status=status)


# ---------- summarize 口径 ----------

def test_summarize_all_pass():
    s = summarize([_finding(status="pass"), _finding(rule_id="F-Y", status="pass")],
                  n_rules=33)
    assert s["overall"] == "pass" and s["overall_label"] == "通过"
    assert s["n_pass"] == 2 and s["n_fail"] == 0 and s["n_need_confirm"] == 0
    assert s["basis_linkage_rate"] == 1.0  # 无非 pass 时记 1.0
    assert s["non_pass_severity"] == {}


def test_summarize_fail_overrides_need_confirm():
    findings = [_finding(status="pass"),
                _finding(rule_id="F-C", status="need_confirm",
                         severity=Severity.NEED_CONFIRM, with_basis=False),
                _finding(rule_id="F-B", severity=Severity.CRITICAL)]
    s = summarize(findings, n_rules=33)
    assert s["overall"] == "fail"  # 有 fail 即不通过
    assert s["n_fail"] == 1 and s["n_need_confirm"] == 1
    assert s["non_pass_severity"] == {"CRITICAL": 1, "NEED_CONFIRM": 1}
    assert s["basis_linkage_rate"] == 0.5  # 非 pass 2 条，1 条挂依据


def test_summarize_only_need_confirm_is_manual_review():
    s = summarize([_finding(status="need_confirm", severity=Severity.NEED_CONFIRM)],
                  n_rules=33)
    assert s["overall"] == "need_confirm" and s["overall_label"] == "需人工复核"


# ---------- 五节点流水线 ----------

def test_build_pipeline_end_to_end_on_real_record():
    pipe = build_pipeline(RECORD)
    ctx = pipe.run()
    assert pipe.success is True
    assert set(ctx[CTX_TIMINGS]) == {"解析", "LLM兜底", "质控", "汇总", "导出"}
    assert ctx["n_rules"] == 33
    s = ctx[CTX_SUMMARY]
    assert s["n_rules"] == 33
    assert s["overall"] == "fail"  # 缺陷记录
    non_pass = [f for f in ctx[CTX_FINDINGS] if f.status != "pass"]
    assert non_pass and s["n_fail"] + s["n_need_confirm"] == len(non_pass)
    # 汇总与结论清单同源可序列化
    json.dumps({f.rule_id: f.to_dict() for f in ctx[CTX_FINDINGS]}, ensure_ascii=False)


def test_build_pipeline_missing_input_fails_pipeline():
    pipe = build_pipeline(REPO_ROOT / "data" / "no_such_dir")
    ctx = pipe.run()
    assert pipe.success is False
    assert any("输入目录不存在" in r.error for r in pipe.results if not r.ok)
    assert [r.name for r in pipe.results] == ["解析"]  # 失败即停


def test_build_pipeline_export_node_writes_docx(tmp_path):
    pytest.importorskip("docx", reason="report extra 未安装：pip install 'mrqc[report]'")
    out = tmp_path / "report.docx"
    pipe = build_pipeline(RECORD, report_path=out)
    ctx = pipe.run()
    assert pipe.success is True
    assert out.is_file()


def test_build_pipeline_without_llm_node():
    """use_llm=False 去掉兜底节点（基准环境纯规则确定性通路）。"""
    pipe = build_pipeline(RECORD, use_llm=False)
    ctx = pipe.run()
    assert pipe.success is True
    assert set(ctx[CTX_TIMINGS]) == {"解析", "质控", "汇总", "导出"}
