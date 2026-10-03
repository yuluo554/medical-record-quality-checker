"""datagen 测试：确定性 RNG、位级可复现、truth 对账、缺陷 ID 表契约、仓内数据集 DoD。

位级可复现（plan/05 §3 DoD）：同 seed 生成两次，全部文件字节一致——
用小规模生成（9 份干净 + 14×2 注入 + 6 对照）保持测试速度，全量数据集
（data/samples、data/paired）的配额与对账在仓内数据上验收（test_repo_datasets_*）。
"""

import hashlib
import json
from pathlib import Path

import pytest

from mrqc.datagen import generate_clean, generate_paired
from mrqc.datagen.inject import INJECTIONS, INJECTION_ORDER
from mrqc.datagen.rng import DetRng
from mrqc.datagen.verify import verify_dataset
from mrqc.knowledge.drugs import classify_drug
from mrqc.models import RecordCard

REPO_ROOT = Path(__file__).resolve().parents[1]

# plan/04 §7 缺陷 ID 表（M1 生成器 / M3 规则 / M4 基准三方共用，锁定防单方改名）
EXPECTED_DEFECT_IDS = (
    "F-REQ-01", "F-SIGN-01", "F-TIME-01", "F-TIME-02", "F-TIME-03",
    "C-DIAG-01", "C-SURG-01", "C-SURG-02", "C-LAB-01", "C-LAB-02",
    "C-ORD-01", "C-ANTI-01", "C-BLOOD-01", "C-TIME-01",
)


def test_knowledge_dir_points_to_repo_data():
    """回归锁定：knowledge_dir 指向仓体 data/knowledge（M0 曾误指 src/data）。"""
    from mrqc.knowledge import knowledge_dir
    kd = knowledge_dir()
    assert kd.name == "knowledge" and kd.parent.name == "data"
    assert (kd.parent / "templates").is_dir()


def test_det_rng_deterministic():
    a, b = DetRng(20261003), DetRng(20261003)
    for _ in range(200):
        assert a.random() == b.random()
        assert a.randint(1, 1000) == b.randint(1, 1000)
        assert a.choice("abcdefgh") == b.choice("abcdefgh")
    pool = list(range(20))
    pa, pb = pool[:], pool[:]
    a.shuffle(pa)
    b.shuffle(pb)
    assert pa == pb


def _tree_hash(root: Path):
    """相对路径 → 内容 sha256（含空目录跳过，只看文件）。"""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out


def test_generate_clean_bit_reproducible(tmp_path):
    d1, d2 = tmp_path / "a", tmp_path / "b"
    generate_clean(d1, count=9, seed=20261003)
    generate_clean(d2, count=9, seed=20261003)
    assert _tree_hash(d1) == _tree_hash(d2)
    assert len(_tree_hash(d1)) > 9 * 5  # 每份至少 5 部件 + truth.json


def test_generate_paired_bit_reproducible(tmp_path):
    d1, d2 = tmp_path / "a", tmp_path / "b"
    generate_paired(d1, per_defect=2, clean_controls=6, seed=20261004)
    generate_paired(d2, per_defect=2, clean_controls=6, seed=20261004)
    assert _tree_hash(d1) == _tree_hash(d2)


def test_generated_datasets_pass_verification(tmp_path):
    clean = generate_clean(tmp_path / "s", count=9, seed=123)
    paired = generate_paired(tmp_path / "p", per_defect=2, clean_controls=6, seed=456)
    rc = verify_dataset(tmp_path / "s")
    rp = verify_dataset(tmp_path / "p")
    assert rc["problems"] == []
    assert rp["problems"] == []
    assert rc["records"] == 9
    assert rp["records"] == 34 and rp["clean"] == 6
    assert set(rp["defect_counts"]) == set(EXPECTED_DEFECT_IDS)


def test_injection_registry_matches_id_table():
    assert tuple(INJECTION_ORDER) == EXPECTED_DEFECT_IDS
    for did in EXPECTED_DEFECT_IDS:
        meta = INJECTIONS[did]
        assert meta.channel in ("formal", "integrity")
        assert meta.check_type in (
            "required_field", "timeliness", "cross_consistency",
            "medication_logic", "lab_logic", "signature_format", "timeline_logic")
        assert meta.diseases and set(meta.diseases) <= {"cap", "appendicitis", "gallstone"}


def test_defects_json_shape(tmp_path):
    generate_paired(tmp_path / "p", per_defect=1, clean_controls=2, seed=7)
    data = json.loads(
        (tmp_path / "p" / "defect_C-LAB-02_01" / "defects.json").read_text(encoding="utf-8"))
    assert data["clean_pair"] is False
    d0 = data["defects"][0]
    assert d0["defect_id"] == "C-LAB-02"
    assert d0["rule_id"] == d0["defect_id"]
    assert d0["expect_status"] == "fail"
    assert d0["also_expect"] == ["C-LAB-01"]
    ctrl = json.loads(
        (tmp_path / "p" / "ctrl_cap_01" / "defects.json").read_text(encoding="utf-8"))
    assert ctrl["clean_pair"] is True and ctrl["defects"] == []


def test_truth_card_matches_drug_dict(tmp_path):
    """truth 的抗菌标记与共用药物字典一致（M2 解析派生同源的契约前提）。"""
    generate_clean(tmp_path / "s", count=9, seed=20261003)
    for truth_path in sorted((tmp_path / "s").glob("*/truth.json")):
        card = RecordCard.from_dict(json.loads(truth_path.read_text(encoding="utf-8")))
        for med in card.medications:
            derived = classify_drug(med.drug_name.value)
            assert med.is_antibiotic.value == derived["is_antibiotic"], truth_path
            assert (med.antibiotic_level.value if med.antibiotic_level else "") \
                == derived["antibiotic_level"]


def test_timeline_sorted_and_events_from_vocabulary(tmp_path):
    generate_clean(tmp_path / "s", count=9, seed=20261003)
    vocabulary = {"入院", "术前讨论", "知情同意", "手术", "术后首次病程", "出院",
                  "入院记录完成", "首次病程记录", "危急值处置", "用血审批"}
    for truth_path in sorted((tmp_path / "s").glob("*/truth.json")):
        card = RecordCard.from_dict(json.loads(truth_path.read_text(encoding="utf-8")))
        times = [ev.time.value for ev in card.timeline if ev.time]
        assert times == sorted(times), truth_path
        for ev in card.timeline:
            assert ev.event in vocabulary, (truth_path, ev.event)


# ---------------------------------------------------------------- 仓内数据集（DoD 验收）

def _repo_dataset_ready(name: str) -> bool:
    d = REPO_ROOT / "data" / name
    return d.is_dir() and any(d.glob("*/truth.json"))


@pytest.mark.skipif(not _repo_dataset_ready("samples"), reason="仓内 data/samples 尚未生成")
class TestRepoDatasets:
    def test_samples_dod(self):
        result = verify_dataset(REPO_ROOT / "data" / "samples")
        assert result["problems"] == []
        assert result["records"] >= 60

    @pytest.mark.skipif(not _repo_dataset_ready("paired"), reason="仓内 data/paired 尚未生成")
    def test_paired_dod(self):
        result = verify_dataset(REPO_ROOT / "data" / "paired")
        assert result["problems"] == []
        assert result["clean"] >= 10
        for did in EXPECTED_DEFECT_IDS:
            assert result["defect_counts"].get(did, 0) >= 3, did

    def test_samples_no_defects_json(self):
        assert list((REPO_ROOT / "data" / "samples").glob("*/defects.json")) == []
