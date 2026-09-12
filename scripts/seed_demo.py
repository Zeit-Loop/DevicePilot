"""Insert a small, repeatable portfolio dataset into the configured database."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.database import Base, SessionLocal, engine


DEMO_DEVICES: tuple[dict[str, Any], ...] = (
    {
        "name": "循环水离心泵",
        "device_type": "Centrifugal Pump",
        "serial_number": "DEMO-PUMP-001",
        "location": "A 厂房泵房",
        "status": "active",
        "fault": {
            "title": "轴承温度升高",
            "description": "运行二十分钟后轴承区域温度明显升高，并伴随轻微摩擦异响。",
            "severity": "high",
            "status": "investigating",
        },
    },
    {
        "name": "仓储温度传感器",
        "device_type": "Temperature Sensor",
        "serial_number": "DEMO-TEMP-002",
        "location": "成品仓库",
        "status": "inactive",
        "fault": {
            "title": "读数间歇中断",
            "description": "最近一小时内出现三次短暂无读数，网络连接状态不稳定。",
            "severity": "medium",
            "status": "open",
        },
    },
    {
        "name": "装配线工业电机",
        "device_type": "Industrial Motor",
        "serial_number": "DEMO-MOTOR-003",
        "location": "B 产线",
        "status": "maintenance",
        "fault": {
            "title": "负载运行时振动异常",
            "description": "电机在高负载阶段振动增大，停机后外观检查未发现松脱部件。",
            "severity": "critical",
            "status": "open",
        },
    },
    {
        "name": "质检视觉控制器",
        "device_type": "Vision Controller",
        "serial_number": "DEMO-VISION-004",
        "location": "质检工位",
        "status": "active",
        "fault": None,
    },
)


def seed_demo_data(
    session_factory: sessionmaker[Session] = SessionLocal,
) -> tuple[int, int]:
    inserted_devices = 0
    inserted_faults = 0
    with session_factory() as session:
        for record in DEMO_DEVICES:
            fault_data = record["fault"]
            device = session.scalar(
                select(models.Device).where(
                    models.Device.serial_number == record["serial_number"]
                )
            )
            if device is None:
                device = models.Device(
                    **{key: value for key, value in record.items() if key != "fault"}
                )
                session.add(device)
                session.flush()
                inserted_devices += 1

            if fault_data is not None:
                existing_fault = session.scalar(
                    select(models.Fault).where(
                        models.Fault.device_id == device.id,
                        models.Fault.title == fault_data["title"],
                    )
                )
                if existing_fault is None:
                    session.add(models.Fault(device_id=device.id, **fault_data))
                    inserted_faults += 1
        session.commit()
    return inserted_devices, inserted_faults


def main() -> None:
    Base.metadata.create_all(engine)
    devices, faults = seed_demo_data()
    print(f"Demo data ready: {devices} device(s), {faults} fault(s) added.")


if __name__ == "__main__":
    main()
