"""datagen：合成病历生成器（M1 数据先行）。

固定 seed 位级可复现（同 seed 重跑 git status 零变化，纳入回归测试）：

    py -X utf8 -m mrqc.datagen --out data/samples --count 60 --seed 20261003
    py -X utf8 -m mrqc.datagen --out data/paired --paired --per-defect 3 --seed 20261004
    py -X utf8 -m mrqc.datagen --verify data/samples data/paired

- samples：干净合成病历（每病种 count/3 份）+ truth.json（参数卡形状真值）；
- paired：注入缺陷配对集（plan/04 §7 缺陷 ID 表逐项 ≥per_defect 份）+ defects.json
  （注入清单：defect_id=规则 ID、注入参数、also_expect）+ 干净对照；
- 注入记录的 truth.json 描述注入后文档实际写了什么（抽取真值），评测期望
  在 defects.json——两份真值分离，M2 解析基准与 M4 检出基准互不干扰。
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .inject import INJECTIONS, INJECTION_ORDER, apply_injection
from .rng import DetRng
from .render import PART_FILENAMES, render_record
from .spec import build_spec, load_templates

__all__ = ["TEMPLATE_ORDER", "generate_clean", "generate_paired",
           "write_record", "clean_defects_json"]

TEMPLATE_ORDER = ("cap", "appendicitis", "gallstone")

_DEFECTS_NOTES = (
    "评测按文档全部非 pass 集合对账；defect_id 与 M3 规则、M4 基准三方共用"
    "（plan/04 §7），不得单方改名。defects 仅主注入；同一注入隐含的其余结论记 also_expect。"
)


def clean_defects_json(record_id: str, template_id: str, seed: int) -> Dict[str, Any]:
    return {
        "record_id": record_id,
        "template_id": template_id,
        "clean_pair": True,
        "seed": seed,
        "defects": [],
        "notes": _DEFECTS_NOTES,
    }


def write_record(record_dir: Path, rendered, template_id: str, seed: int,
                 defects: Optional[list] = None) -> None:
    """落盘一份记录：部件 txt（文件名固定 ASCII）+ truth.json（+ defects.json）。"""
    record_dir.mkdir(parents=True, exist_ok=True)
    for part, text in rendered.parts.items():
        path = record_dir / PART_FILENAMES[part]
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    with open(record_dir / "truth.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rendered.card.to_dict(), ensure_ascii=False, indent=2) + "\n")
    if defects is not None:  # None = 干净 samples 集，不写 defects.json
        payload = {
            "record_id": record_dir.name,
            "template_id": template_id,
            "clean_pair": not defects,
            "seed": seed,
            "defects": defects,
            "notes": _DEFECTS_NOTES,
        }
        with open(record_dir / "defects.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _next_seed(master: DetRng) -> int:
    return master.randint(10 ** 7, 10 ** 9)


def generate_clean(out_dir: Path, count: int, seed: int) -> Dict[str, Any]:
    """干净合成病历集：count 按 3 病种轮转均分。"""
    templates = load_templates()
    master = DetRng(seed)
    hospital_seq = 0
    per_disease: Dict[str, int] = {}
    for i in range(count):
        tid = TEMPLATE_ORDER[i % len(TEMPLATE_ORDER)]
        n = i // len(TEMPLATE_ORDER) + 1
        record_id = "%s_%03d" % (tid, n)
        spec = build_spec(templates[tid], DetRng(_next_seed(master)), hospital_seq, record_id)
        hospital_seq += 1
        rendered = render_record(spec)
        write_record(out_dir / record_id, rendered, tid, seed)
        per_disease[tid] = per_disease.get(tid, 0) + 1
    return {"out": str(out_dir), "count": count, "seed": seed, "per_disease": per_disease}


def generate_paired(out_dir: Path, per_defect: int = 3, clean_controls: int = 12,
                    seed: int = 20261004) -> Dict[str, Any]:
    """注入缺陷配对集：每个缺陷 ID ≥per_defect 份 + 干净对照 clean_controls 份。"""
    templates = load_templates()
    master = DetRng(seed)
    hospital_seq = 0
    made: Dict[str, int] = {}
    for defect_id in INJECTION_ORDER:
        meta = INJECTIONS[defect_id]
        for k in range(1, per_defect + 1):
            tid = meta.diseases[(k - 1) % len(meta.diseases)]
            record_id = "defect_%s_%02d" % (defect_id, k)
            spec = build_spec(templates[tid], DetRng(_next_seed(master)), hospital_seq, record_id)
            hospital_seq += 1
            params = apply_injection(defect_id, spec, templates[tid], DetRng(_next_seed(master)), k)
            if params is None:
                raise KeyError("未注册的缺陷 ID：%s" % defect_id)
            rendered = render_record(spec)
            defect_entry = [{
                "defect_id": defect_id,
                "rule_id": defect_id,
                "channel": meta.channel,
                "check_type": meta.check_type,
                "description": meta.description,
                "expect_status": "fail",
                "also_expect": list(meta.also_expect),
                "params": params,
            }]
            write_record(out_dir / record_id, rendered, tid, seed, defects=defect_entry)
            made[defect_id] = made.get(defect_id, 0) + 1
    # 干净对照（胆囊结石一半带"用血+审批"变体，验证用血规则不误报）
    controls: Dict[str, int] = {}
    for i in range(clean_controls):
        tid = TEMPLATE_ORDER[i % len(TEMPLATE_ORDER)]
        idx = i // len(TEMPLATE_ORDER) + 1
        record_id = "ctrl_%s_%02d" % (tid, idx)
        force_blood = (idx % 2 == 0) if tid == "gallstone" else None
        spec = build_spec(templates[tid], DetRng(_next_seed(master)), hospital_seq, record_id,
                          force_blood=force_blood)
        hospital_seq += 1
        rendered = render_record(spec)
        write_record(out_dir / record_id, rendered, tid, seed, defects=[])
        controls[tid] = controls.get(tid, 0) + 1
    return {"out": str(out_dir), "seed": seed, "per_defect": per_defect,
            "defect_records": made, "clean_controls": clean_controls, "controls": controls}
