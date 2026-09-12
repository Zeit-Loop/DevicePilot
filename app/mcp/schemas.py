from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import DeviceStatus, FaultSeverity, FaultStatus


class DeviceDTO(BaseModel):
    id: int
    name: str
    device_type: str
    serial_number: str
    location: str | None
    status: DeviceStatus
    created_at: datetime
    updated_at: datetime


class FaultHistoryItemDTO(BaseModel):
    id: int
    device_id: int
    title: str
    description: str = Field(max_length=500)
    severity: FaultSeverity
    status: FaultStatus
    created_at: datetime


class RecentFaultsResult(BaseModel):
    device_id: int
    faults: list[FaultHistoryItemDTO]


class KnowledgeMatchDTO(BaseModel):
    document: str
    chunk_index: int = Field(ge=0)
    content: str
    equipment_type: str


class KnowledgeSearchResult(BaseModel):
    device_id: int
    matches: list[KnowledgeMatchDTO] = Field(max_length=3)
