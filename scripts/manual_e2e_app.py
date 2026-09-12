"""Deterministic backend used only for local manual Phase 3 browser checks."""

from pathlib import Path

from sqlalchemy import select

from app import models, schemas
from app.database import create_database, create_session_factory
from app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "devicepilot-manual-e2e.db"
TEST_DEVICE_SERIAL = "MANUAL-E2E-001"

MOCK_DIAGNOSIS_RESULT = schemas.DiagnosisResult(
    risk_level=schemas.RiskLevel.high,
    summary="设备发热并伴随摩擦异响，可能存在较严重的机械故障。完成检查前请保持设备停机。",
    possible_causes=[
        "轴承磨损或失效",
        "润滑不足",
        "轴或转子未对中",
    ],
    recommended_checks=[
        "检查前切断并隔离电源",
        "按规范检查轴承温度和间隙",
        "检查润滑剂余量和污染情况",
    ],
    recommended_actions=[
        "保持泵设备停机",
        "安排合格的维修人员检查",
        "根据检查结果更换损坏的轴承或润滑部件",
    ],
)


def deterministic_diagnosis(
    _device: models.Device, _description: str
) -> schemas.DiagnosisResult:
    return MOCK_DIAGNOSIS_RESULT


engine = create_database(f"sqlite:///{DATABASE_PATH.as_posix()}")
session_factory = create_session_factory(engine)
app = create_app(
    session_factory=session_factory,
    engine=engine,
    diagnosis_service=deterministic_diagnosis,
)


def seed_test_device() -> None:
    with session_factory() as session:
        existing = session.scalar(
            select(models.Device).where(
                models.Device.serial_number == TEST_DEVICE_SERIAL
            )
        )
        if existing is not None:
            return
        session.add(
            models.Device(
                name="人工验证冷却泵",
                device_type="离心泵",
                serial_number=TEST_DEVICE_SERIAL,
                location="A 厂房 / 测试区",
                status=schemas.DeviceStatus.active.value,
            )
        )
        session.commit()


seed_test_device()
