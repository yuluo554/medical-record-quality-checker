"""packaging 守门：知识库必须随包分发（非 editable 安装下同样可用）。

P0 回归（二次迭代）：`knowledge_dir()` 曾用 `parents[3]` 算路径，装成 wheel 后在
site-packages 下解析到不存在的 `<venv>/Lib/data/knowledge` → 规则库 0 条 → 所有
结论「通过」且退出码 0。本文件把「知识库在包内 + package-data 已声明 + 数据文件在
源码树里」三条锁死，让这类缺陷在装态复现前先在测试层暴露。

注意：本文件的断言全部基于**源码树**（`src/mrqc/knowledge/data/`）。真正的装态验收
（pip install <wheel> 后在仓外跑 check）由批次一/批次五的门禁命令承担。
"""

import re
from pathlib import Path

import mrqc.knowledge
from mrqc.knowledge import knowledge_dir, knowledge_status

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_knowledge_dir_inside_package():
    """knowledge_dir() 必须落在包目录内（src/mrqc/knowledge/data），不是仓根 data/。"""
    pkg_dir = Path(mrqc.knowledge.__file__).resolve().parent
    assert pkg_dir.name == "knowledge", pkg_dir
    kd = knowledge_dir()
    assert kd == pkg_dir / "data", kd
    # 反向锁：不得再解析回仓体 data/knowledge（M0/M3 前的形态）
    assert kd != (REPO_ROOT / "data" / "knowledge"), kd


def test_knowledge_counts():
    """包内知识库读得到 33 条规则 / 42 个条文块（0 条即 P0 复发）。"""
    s = knowledge_status()
    assert s["rules"] == 33, s
    assert s["blocks"] == 42, s


def test_package_data_declared():
    """pyproject.toml 必须声明 [tool.setuptools.package-data] 让 blocks/rules 进 wheel。"""
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in text, "缺 package-data 段"
    block = text.split("[tool.setuptools.package-data]", 1)[1]
    # 取到下一个 section 头之前
    block = re.split(r"\n\[", block, 1)[0]
    assert '"mrqc.knowledge"' in block, block
    assert "data/blocks/*.json" in block, block
    assert "data/rules/*.json" in block, block


def test_package_data_files_present():
    """源码树里包内 blocks 5 份 / rules 2 份 json 存在且非空。"""
    blocks = sorted((knowledge_dir() / "blocks").glob("*.json"))
    rules = sorted((knowledge_dir() / "rules").glob("*.json"))
    assert len(blocks) == 5, [p.name for p in blocks]
    assert len(rules) == 2, [p.name for p in rules]
    for path in blocks + rules:
        assert path.stat().st_size > 0, path
        assert path.suffix == ".json", path