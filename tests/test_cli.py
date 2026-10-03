"""CLI 测试：demo 自检、parse 空目录告警、未实现子命令退出码 2。"""

import pytest

import mrqc
from mrqc.cli import main


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
