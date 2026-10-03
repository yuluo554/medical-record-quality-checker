"""CLI 测试：demo 自检、parse 空目录告警、未实现子命令退出码 2、benchmark parse 基准。"""

import json
import shutil
from pathlib import Path

import pytest

import mrqc
from mrqc.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert mrqc.__version__ in capsys.readouterr().out


def test_demo_runs(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "病历参数卡" in out
    assert "路线图" in out
    assert "不是临床决策支持工具" in out


def test_parse_missing_dir_reports_warning(tmp_path, capsys):
    rc = main(["parse", "--input", str(tmp_path / "no_such_dir")])
    assert rc == 0  # 输入目录缺失走告警通路不崩溃
    out = capsys.readouterr().out
    assert "no_such_dir" in out


def test_check_with_empty_rules(tmp_path):
    (tmp_path / "record.txt").write_text("随便一段不属于任何部件的文本", encoding="utf-8")
    rc = main(["check", "--input", str(tmp_path)])
    assert rc == 0


def test_run_end_to_end_prints_conclusion_json(capsys):
    """M5 run：五节点端到端 → stdout 结论 JSON（含分级统计），rc=0。"""
    rc = main(["run", "--input", str(REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01")])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["record_id"] == "defect_C-LAB-02_01"
    assert data["summary"]["overall"] == "fail"
    assert data["summary"]["n_rules"] == 33
    assert any(f["status"] != "pass" for f in data["findings"])
    assert set(data["timings"]) == {"解析", "LLM兜底", "质控", "汇总", "导出"}


def test_run_report_exports_docx(tmp_path, capsys):
    pytest.importorskip("docx", reason="report extra 未安装：pip install 'mrqc[report]'")
    out = tmp_path / "r.docx"
    rc = main(["run", "--input", str(REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01"),
               "--report", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "已导出 docx" in capsys.readouterr().err


def test_run_report_missing_dep_exit_2(tmp_path, monkeypatch, capsys):
    """--report 依赖预检：缺 python-docx 时 exit 2 + 安装提示（不跑完质控才失败）。"""
    import mrqc.report as report_mod

    monkeypatch.setattr(report_mod, "docx_available", lambda: False)
    rc = main(["run", "--input", str(REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01"),
               "--report", str(tmp_path / "x.docx")])
    assert rc == 2
    assert "pip install 'mrqc[report]'" in capsys.readouterr().err


def test_run_missing_input_exit_1(tmp_path, capsys):
    rc = main(["run", "--input", str(tmp_path / "nope")])
    assert rc == 1
    assert "输入目录不存在" in capsys.readouterr().err


def test_benchmark_no_name_exit_2():
    assert main(["benchmark"]) == 2


def test_benchmark_parse_on_subset(tmp_path, capsys):
    """mrqc benchmark parse：小样架子集跑通，F1=1.0（基准环境零 LLM 依赖）。"""
    src = REPO_ROOT / "data" / "samples"
    for name in ("cap_001", "appendicitis_001", "gallstone_001"):
        shutil.copytree(src / name, tmp_path / name)
    rc = main(["benchmark", "parse", "--data", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    r = json.loads(out[out.index("{"):])
    assert r["n_records"] == 3
    assert r["f1"] == 1.0
    assert r["records_with_evidence_violations"] == 0


def test_benchmark_parse_missing_dir_exit_2(tmp_path):
    assert main(["benchmark", "parse", "--data", str(tmp_path / "nope")]) == 2


def test_benchmark_detect_on_paired(capsys):
    """mrqc benchmark detect：配对集端到端检出，M4 门槛（误报 0 + 检出率 ≥0.95）。"""
    rc = main(["benchmark", "detect", "--data", str(REPO_ROOT / "data" / "paired")])
    assert rc == 0
    out = capsys.readouterr().out
    r = json.loads(out[out.index("{"):])
    assert r["detection_rate"] >= 0.95
    assert r["clean_false_positives"] == 0
    assert r["unexpected_findings"] == 0


def test_benchmark_detect_gate_fails_on_impossible_threshold(capsys):
    rc = main(["benchmark", "detect", "--data", str(REPO_ROOT / "data" / "paired"),
               "--min-detection-rate", "1.1"])
    assert rc == 1
    assert "未达标" in capsys.readouterr().err


def test_benchmark_detect_missing_dir_exit_2(tmp_path):
    assert main(["benchmark", "detect", "--data", str(tmp_path / "nope")]) == 2
