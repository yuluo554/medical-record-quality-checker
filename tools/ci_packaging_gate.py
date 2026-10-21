"""CI 打包门禁：非 editable 装态验活（跨 OS 稳健，P0 回归守门）。

步骤（全用 Python 处理路径，规避 Windows/Git-Bash 的 MSYS 路径改写）：
  1. python -m build --wheel  → 临时目录
  2. 全新 venv 装 wheel（**不带 -e**）
  3. 在中立临时目录（仓外）跑 `mrqc check`
  4. 断言：knowledge_status()['rules']==33 / ['blocks']==42，check → 33 条 finding

改前行为（P0）：装 wheel 后 knowledge_dir() 解析到 <venv>/Lib/data/knowledge（不存在）
→ 规则库 0 条 → check 输出 []、"总体结论：通过"、退出码 0。本门禁让它在 CI 上立刻红。

本地运行：python tools/ci_packaging_gate.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "data" / "samples" / "appendicitis_001"


def _run(args, **kw):
    print("+", " ".join(str(a) for a in args), flush=True)
    return subprocess.run([str(a) for a in args], **kw)


def _venv_python(venv: Path) -> Path:
    for rel in ("Scripts/python.exe", "bin/python"):
        p = venv / rel
        if p.exists():
            return p
    raise SystemExit("找不到 venv 内的 python：%s" % venv)


def main() -> int:
    work = Path(os.environ.get("RUNNER_TEMP") or __import__("tempfile").gettempdir())
    work = work / "mrqc-pkg-gate"
    dist = work / "dist"
    venv = work / "venv"
    neutral = work / "neutral"
    for d in (dist, neutral):
        d.mkdir(parents=True, exist_ok=True)
    if venv.exists():
        __import__("shutil").rmtree(venv)

    # 1) 构建 wheel（用当前解释器）
    if _run([sys.executable, "-m", "build", "--wheel", "--outdir", dist],
            cwd=REPO_ROOT).returncode != 0:
        return 1
    wheels = sorted(dist.glob("*.whl"))
    assert wheels, "未产出 wheel"
    wheel = wheels[-1]
    print("wheel:", wheel)

    # 2) 全新 venv + 装 wheel（不带 -e）
    if _run([sys.executable, "-m", "venv", venv]).returncode != 0:
        return 1
    vpy = _venv_python(venv)
    if _run([vpy, "-m", "pip", "install", wheel]).returncode != 0:
        return 1

    # 3) 仓外中立目录跑 knowledge_status + check
    probe = ("from mrqc.knowledge import knowledge_status; "
             "s = knowledge_status(); print(s); "
             "assert s['rules'] == 33 and s['blocks'] == 42, s")
    if _run([vpy, "-c", probe], cwd=neutral).returncode != 0:
        return 1

    out = neutral / "check.json"
    err = neutral / "check.err"
    with open(out, "wb") as fo, open(err, "wb") as fe:
        rc = _run([vpy, "-m", "mrqc.cli", "check", "--input", SAMPLE],
                  cwd=neutral, stdout=fo, stderr=fe).returncode
    print(err.read_text(encoding="utf-8", errors="replace"), flush=True)
    if rc != 0:
        print("[FAIL] check 退出码 %d（期望 0）" % rc, file=sys.stderr)
        return 1
    findings = json.loads(out.read_text(encoding="utf-8"))
    print("findings:", len(findings), flush=True)
    if len(findings) != 33:
        print("[FAIL] findings=%d（期望 33；0 条即 P0 复发）" % len(findings), file=sys.stderr)
        return 1
    print("PACKAGING GATE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())