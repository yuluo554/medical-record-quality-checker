"""CLI 控制台编码守门：非 UTF-8 输出流下中文输出不得崩。

背景（CI windows 腿实测）：Windows 默认控制台编码是 cp1252/gbk，`mrqc demo` 打印
中文标题时 UnicodeEncodeError → 退出码 1。CI 的 windows 腿第一次跑就暴露了它
（此前 CI 只有 ubuntu 一个 OS 维度）。修法：cli._force_utf8_stdio() 把 stdout/stderr
切到 UTF-8。

本测试在**子进程**里用 PYTHONIOENCODING=cp1252 强制成非 UTF-8 流，验证 CLI 仍 rc=0
（移除守卫即变红）。
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli_cp1252(args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    # 显式指向本仓 src：子进程 `-m mrqc.cli` 若继承到已装的另一个 mrqc（如 sdist
    # 环境里 site-packages 的旧副本）会测错对象——实测 sdist 下就栽在这里。
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "mrqc.cli", *args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def test_demo_survives_cp1252_console():
    proc = _run_cli_cp1252(["demo"])
    assert proc.returncode == 0, (
        "cp1252 输出流下 CLI 崩了（退出码 %d）：\n%s" % (proc.returncode, proc.stderr[-1500:])
    )
    assert "出院病历内涵质控" in proc.stdout


def test_force_utf8_stdio_reconfigures_non_utf8_streams():
    from mrqc.cli import _force_utf8_stdio

    # 已替换/可通过 reconfigure 的流：调用后 encoding 归 UTF-8（有 reconfigure 时）
    class FakeStream:
        encoding = "cp1252"

        def __init__(self):
            self.calls = []

        def reconfigure(self, **kw):
            self.calls.append(kw)
            self.encoding = kw.get("encoding", self.encoding)

    fake_out, fake_err = FakeStream(), FakeStream()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = fake_out, fake_err
    try:
        _force_utf8_stdio()
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    assert fake_out.calls and fake_out.calls[0]["encoding"] == "utf-8"
    assert fake_err.calls and fake_err.calls[0]["encoding"] == "utf-8"