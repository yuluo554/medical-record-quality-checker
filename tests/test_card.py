"""病历参数卡契约测试：schema 往返、字段包装约束。"""

import pytest

from mrqc.models import (
    Diagnosis,
    Evidence,
    FieldValue,
    MedicationOrder,
    PatientInfo,
    RecordCard,
    Surgery,
)


def test_field_value_confidence_bounds():
    with pytest.raises(ValueError):
        FieldValue(value=1, confidence=1.5)
    with pytest.raises(ValueError):
        FieldValue(value=1, confidence=-0.1)
    fv = FieldValue(value="张三", confidence=0.0)
    assert fv.confidence == 0.0


def test_record_card_roundtrip():
    card = RecordCard(
        patient=PatientInfo(
            name=FieldValue(value="张三", evidence=[Evidence(part="入院记录", quote="姓名：张三")]),
            age=FieldValue(value=45, unit="岁"),
        ),
        diagnoses=[Diagnosis(type="出院", name=FieldValue(value="急性阑尾炎"))],
        surgeries=[Surgery(name=FieldValue(value="腹腔镜阑尾切除术"), surgeon=FieldValue(value="李四"))],
        medications=[
            MedicationOrder(
                drug_name=FieldValue(value="头孢呋辛钠"),
                is_antibiotic=FieldValue(value=True),
                antibiotic_level=FieldValue(value="非限制使用级"),
            )
        ],
        parse_warnings=["无法识别部件：foo.txt"],
    )
    restored = RecordCard.from_dict(card.to_dict())
    assert restored == card
    assert restored.patient.name.evidence[0].quote == "姓名：张三"
    assert restored.medications[0].is_antibiotic.value is True
    assert restored.parse_warnings == ["无法识别部件：foo.txt"]


def test_empty_card_roundtrip():
    card = RecordCard()
    assert RecordCard.from_dict(card.to_dict()) == card
    d = card.to_dict()
    assert d["patient"]["name"] is None
    assert d["medications"] == []
