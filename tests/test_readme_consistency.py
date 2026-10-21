"""README 自述测试数守门：README 写的「N 项」必须等于真实收集数。

背景（姊妹项目实测教训）：README/留档里的测试数会在「加测试忘改文档」时漂移，
而错误数字会随 tag 进入 Release。这里把 README 快速开始处的数字与 pytest 实际
收集数锁在一起——加测试后必须同步 README，否则本测试变红。

实现说明：用子进程 `--collect-only -q` 取真实收集数（不执行测试，故无递归执行
风险；`-o addopts=""` 绕开本仓 addopts="-q" 叠加成 -qq 吞掉汇总行的问题）。
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"


def _readme_test_count() -> int:
    text = README.read_text(encoding="utf-8")
    m = re.search(r"全离线测试（含 extras 守门）：(\d+)\s*项", text)
    assert m, "README 快速开始处未找到「全离线测试（含 extras 守门）：N 项」"
    return int(m.group(1))


def _collected_count() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) tests? collected", out)
    assert m, "未能从 pytest 收集输出解析测试数：\n%s" % out[-2000:]
    return int(m.group(1))


def test_readme_reported_test_count_matches_collected():
    assert _readme_test_count() == _collected_count(), (
        "README 自述 %d 项 ≠ 实际收集 %d 项——加/删测试后请同步 README 快速开始行"
        % (_readme_test_count(), _collected_count())
    )