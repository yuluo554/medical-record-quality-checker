"""药物字典：抗菌药物分级与血液制品标记（datagen 真值派生 / M2 解析派生共用）。

纪律：生成器写进 truth.json 的 is_antibiotic / antibiotic_level 必须与解析器
从同一医嘱文本派生的结果一致——两边共用本字典，不许各自维护。
等级口径：《抗菌药物临床应用管理办法》三级管理（非限制级/限制级/特殊使用级）。
"""

from typing import Any, Dict, Optional

__all__ = ["ANTIBIOTIC_LEVELS", "BLOOD_PRODUCTS", "lookup_drug", "classify_drug", "is_blood_product"]

ANTIBIOTIC_LEVELS = ("非限制级", "限制级", "特殊使用级")

# 血液制品（供 C-BLOOD-01 术中用血闭环规则识别；品种按临床常用血浆制品口径）
BLOOD_PRODUCTS = (
    "去白细胞悬浮红细胞",
    "悬浮红细胞",
    "新鲜冰冻血浆",
    "机采血小板",
    "冷沉淀",
)

# 医嘱单出现的药物 → 抗菌标记 + 分级（空串 = 非抗菌药物）
_DRUG_DB: Dict[str, Dict[str, Any]] = {
    # 抗菌药物（CAP / 外科预防与治疗常用）
    "注射用头孢呋辛钠": {"is_antibiotic": True, "antibiotic_level": "非限制级"},
    "阿奇霉素注射液": {"is_antibiotic": True, "antibiotic_level": "非限制级"},
    "左氧氟沙星注射液": {"is_antibiotic": True, "antibiotic_level": "限制级"},
    "头孢哌酮舒巴坦钠": {"is_antibiotic": True, "antibiotic_level": "限制级"},
    "甲硝唑注射液": {"is_antibiotic": True, "antibiotic_level": "非限制级"},
    "注射用亚胺培南西司他丁钠": {"is_antibiotic": True, "antibiotic_level": "特殊使用级"},
    # 非抗菌药物
    "盐酸氨溴索注射液": {"is_antibiotic": False, "antibiotic_level": ""},
    "对乙酰氨基酚片": {"is_antibiotic": False, "antibiotic_level": ""},
    "0.9%氯化钠注射液": {"is_antibiotic": False, "antibiotic_level": ""},
    "5%葡萄糖注射液": {"is_antibiotic": False, "antibiotic_level": ""},
    "阿托品注射液": {"is_antibiotic": False, "antibiotic_level": ""},
    "苯巴比妥钠注射液": {"is_antibiotic": False, "antibiotic_level": ""},
}


def lookup_drug(drug_name: str) -> Optional[Dict[str, Any]]:
    """按医嘱药名精确查字典；查不到返回 None（调用方自行决定兜底）。"""
    return _DRUG_DB.get(drug_name.strip())


def classify_drug(drug_name: str) -> Dict[str, Any]:
    """派生抗菌标记与分级；未收录药物按非抗菌处理（保守口径）。"""
    hit = lookup_drug(drug_name)
    if hit:
        return {"is_antibiotic": hit["is_antibiotic"], "antibiotic_level": hit["antibiotic_level"]}
    return {"is_antibiotic": False, "antibiotic_level": ""}


def is_blood_product(drug_name: str) -> bool:
    """血液制品判定（输血医嘱识别，供用血审批闭环）。"""
    return any(b in drug_name for b in BLOOD_PRODUCTS)
