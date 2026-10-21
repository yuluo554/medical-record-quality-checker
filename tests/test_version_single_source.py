"""版本单一来源守门：pyproject.toml 的 version 必须等于 mrqc.__version__。

改一处忘另一处（本仓历史上两处手写）会让「装出来的包版本」与「代码自报版本」
不一致——发布/审计时会误判。负控：把其中一处改成别的值，本测试即红。
"""

import re
import tomllib
from pathlib import Path

import mrqc

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pyproject_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_version_single_source():
    assert mrqc.__version__ == _pyproject_version(), (
        "版本号不一致：__init__.__version__=%r vs pyproject=%r"
        % (mrqc.__version__, _pyproject_version())
    )


def test_version_is_pep440_like():
    assert re.match(r"^\d+\.\d+\.\d+", mrqc.__version__), mrqc.__version__