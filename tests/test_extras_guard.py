"""extras 守门测试：依赖分层声明必须覆盖运行期与测试期真实 import。

背景（姊妹项目实测教训）：
- FastAPI UploadFile 需要 python-multipart，漏声明时 uvicorn 启动即崩；
- 测试期依赖缺失会让整模块静默跳过（dev 绿但悄悄少跑）。
本测试静态锁定 pyproject extras 声明与 CI 安装范围。
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _extras_section() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"\[project\.optional-dependencies\](.*?)(?=\n\[|\Z)", text, re.S)
    assert m, "pyproject.toml 缺少 [project.optional-dependencies] 节"
    return m.group(1)


def _extra_block(section: str, name: str) -> str:
    m = re.search(r"^%s\s*=\s*\[(.*?)\]" % name, section, re.S | re.M)
    assert m, "extras 缺少 %s 组" % name
    return m.group(1)


def test_web_extra_declares_python_multipart():
    web = _extra_block(_extras_section(), "web")
    assert "python-multipart" in web, "web extra 必须声明 python-multipart（UploadFile 运行期依赖）"
    for pkg in ("fastapi", "uvicorn"):
        assert pkg in web


def test_report_and_dev_extras_declared():
    section = _extras_section()
    assert "python-docx" in _extra_block(section, "report")
    assert "pytest" in _extra_block(section, "dev")


def test_lazy_import_guards_present():
    """report/web 必须带惰性导入守卫（缺依赖给安装提示，exit 2 不崩）。"""
    web_init = (ROOT / "src" / "mrqc" / "web" / "__init__.py").read_text(encoding="utf-8")
    assert "_import_fastapi" in web_init and "pip install" in web_init
    report_init = (ROOT / "src" / "mrqc" / "report" / "__init__.py").read_text(encoding="utf-8")
    assert "_import_docx" in report_init and "pip install" in report_init


def test_ci_installs_all_extras():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '.[dev,web,report]"' in ci, "CI 必须显式安装全量 extras（防静默少跑）"
    assert '"3.8"' in ci, "CI 必须覆盖 Python 3.8 底线（requires-python 对齐）"
