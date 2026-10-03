"""报告导出层（docx）。依赖属可选 extra，惰性导入：缺依赖给安装提示不崩。"""

from pathlib import Path
from typing import List


def _import_docx():
    """惰性导入 python-docx；缺失时抛带安装提示的 ImportError。"""
    try:
        import docx  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "质控报告导出需要 python-docx：请安装报告组件 pip install 'mrqc[report]'"
        ) from exc


def export_report(card, findings: List, out_path: Path) -> Path:
    """导出 docx 质控报告：结论+分级缺陷清单+逐条证据+整改建议+质控医师签署栏。

    M5 实现（plan/05 里程碑 M5）；报告首页必须带"非临床决策支持"免责声明。
    """
    _import_docx()
    raise NotImplementedError("docx 报告导出在 M5 实现（plan/05 里程碑 M5）")
