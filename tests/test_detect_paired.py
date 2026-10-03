"""配对集端到端检出回归（M3 首版口径，M4 门槛预演）。

跑通 data/paired 全量 54 份并对账 defects.json：
- 干净对照 12 份：非 pass 结论必须为 0（M4 正式门槛，本测试持续守门）；
- 缺陷记录 42 份：主缺陷规则必须命中；期望之外的非 pass 结论必须为 0；
- 依据关联率 100%（非 pass 结论全挂 basis）。
"""

import sys
from pathlib import Path

from mrqc.eval.detect import evaluate_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
PAIRED = REPO_ROOT / "data" / "paired"


def _results():
    return evaluate_dataset(PAIRED)


def test_clean_controls_zero_false_positives():
    r = _results()
    assert r["n_clean_records"] == 12
    assert r["clean_false_positives"] == 0, r["clean_fp_detail"]


def test_all_defect_ids_fully_detected():
    r = _results()
    assert r["n_records"] == 54
    assert r["missed_detail"] == []
    assert r["unexpected_findings"] == 0
    assert r["detection_rate"] == 1.0
    # 14 个缺陷 ID 每个都应 3/3 检出
    assert len(r["per_defect_detection"]) == 14
    assert all(hit == 3 for hit, _ in r["per_defect_detection"].values())


def test_basis_linkage_complete():
    r = _results()
    assert r["basis_linkage_rate"] == 1.0
    assert r["n_non_pass_findings"] == 45  # 42 主缺陷 + 3 条 C-LAB-02 隐含 C-LAB-01


def test_unverified_timeliness_detected_as_need_confirm():
    """F-TIME-03 以 need_confirm 形式检出（待核对依据纪律），计入非 pass。"""
    r = _results()
    ft3 = [d for d in r["details"] if d["expected_main"] == ["F-TIME-03"]]
    assert len(ft3) == 3
    for d in ft3:
        assert len(d["detected_non_pass"]) == 1
        assert d["detected_non_pass"][0]["status"] == "need_confirm"
