"""CI 工作流结构守门：矩阵形状必须与声明的支持面一致（DEC-2=A）。

锁三件事：
① ci.yml 可被 YAML 解析（防手改出的语法错误）；
② test job 的矩阵覆盖**两个 OS** × 声明的 floor（3.12），不再只跑 ubuntu；
③ 文件里不得残留 3.8 字面量（floor 已收窄，残留即声明与矩阵不一致）。

依赖 pyyaml（dev extra）。
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="缺 pyyaml：pip install 'mrqc[dev]'")

CI_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def ci_text():
    return CI_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ci_doc(ci_text):
    return yaml.safe_load(ci_text)


def test_ci_yaml_parses(ci_doc):
    assert isinstance(ci_doc, dict)
    assert "jobs" in ci_doc and "test" in ci_doc["jobs"]


def test_ci_matrix_covers_two_os_and_floor(ci_doc):
    matrix = ci_doc["jobs"]["test"]["strategy"]["matrix"]
    assert len(matrix["os"]) == 2, matrix
    assert set(matrix["os"]) == {"ubuntu-latest", "windows-latest"}, matrix["os"]
    assert matrix["python-version"] == ["3.12"], matrix["python-version"]


def test_ci_no_stale_python_floor(ci_text):
    """floor 已从 3.8 收窄：矩阵/文件里不得再出现 3.8、3.10 字面量。"""
    assert '"3.8"' not in ci_text and "'3.8'" not in ci_text
    assert '"3.10"' not in ci_text
    assert "3.8" not in ci_text, "ci.yml 仍含 3.8 字面量"


def test_ci_runs_on_matrix_os(ci_doc):
    """runs-on 必须绑定 matrix.os（否则双 OS 维度形同虚设）。"""
    runs_on = ci_doc["jobs"]["test"]["runs-on"]
    assert "matrix.os" in runs_on, runs_on


def test_ci_has_non_editable_packaging_gate(ci_text):
    """P0 回归：CI 必须有一条**非 editable**（装 wheel、仓外目录）的知识库验活步骤。"""
    assert "mypyc" not in ci_text  # 无关噪声
    assert re.search(r"build --wheel", ci_text), "缺 wheel 构建步骤"
    # 装 wheel 时不得带 -e（editable 会掩盖包数据缺陷）
    assert "pip install -e" not in ci_text.split("Packaging gate")[1], \
        "打包门禁步骤不得用 editable 安装"


def test_ci_actions_pinned_v7(ci_text):
    """actions 升到 v7（避免 Node20 弃用注解）。"""
    assert "actions/checkout@v7" in ci_text
    assert "actions/setup-python@v7" in ci_text