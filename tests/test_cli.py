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


def test_run_report_and_benchmark_not_implemented(tmp_path):
    assert main(["run", "--input", str(tmp_path), "--report", "out.docx"]) == 2
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
