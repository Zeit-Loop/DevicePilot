from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class DeviceStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    maintenance = "maintenance"


class FaultSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FaultStatus(str, Enum):
    open = "open"
    investigating = "investigating"
    resolved = "resolved"


class DeviceData(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    device_type: str = Field(min_length=1, max_length=80)
    serial_number: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    status: DeviceStatus = DeviceStatus.active


class DeviceCreate(DeviceData):
    @field_validator("name", "serial_number", mode="before")
    @classmethod
    def trim_required_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DeviceUpdate(DeviceCreate):
    pass


class DeviceRead(DeviceData):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class FaultData(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)
    severity: FaultSeverity = FaultSeverity.medium
    status: FaultStatus = FaultStatus.open


class FaultCreate(FaultData):
    @field_validator("title", "description", mode="before")
    @classmethod
    def trim_required_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class FaultStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FaultStatus


class FaultRead(FaultData):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    created_at: datetime


class RiskLevel(str, Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


class DiagnosisRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


DiagnosisText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class DiagnosisSource(BaseModel):
    document: DiagnosisText
    chunk_index: int = Field(ge=0)


class DiagnosisResult(BaseModel):
    risk_level: RiskLevel
    summary: DiagnosisText
    possible_causes: list[DiagnosisText] = Field(min_length=1)
    recommended_checks: list[DiagnosisText] = Field(min_length=1)
    recommended_actions: list[DiagnosisText] = Field(min_length=1)
    sources: list[DiagnosisSource] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
