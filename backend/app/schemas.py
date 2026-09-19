"""Pydantic 请求 / 响应模型。时间统一接收 ISO 8601 字符串（无时区按本地时间）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- 子资源 ----------
class CasterIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, description="铸机编号，如 CC1")
    name: str = Field(..., min_length=1, max_length=128)
    cycle_minutes: float = Field(..., gt=0, le=600)
    hold_tolerance_minutes: float = Field(15.0, ge=0, le=300)
    capacity_heats: Optional[int] = Field(None, ge=0)
    capacity_tonnes: Optional[float] = Field(None, ge=0)


class CasterOut(CasterIn):
    id: int

    class Config:
        from_attributes = True


class LadleIn(BaseModel):
    seq: int = Field(..., ge=1, description="炉次号")
    arrival: datetime
    grade: str = ""
    weight_tonnes: float = Field(120.0, gt=0, le=500)
    caster_code: Optional[str] = Field(None, description="人工指定铸机；空=自动分配")


class LadleOut(LadleIn):
    id: int
    arrival: datetime

    class Config:
        from_attributes = True


class DowntimeIn(BaseModel):
    caster_code: str
    start: datetime
    end: datetime
    reason: str = "设备维护"

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError("停机结束时间必须晚于开始时间")
        return v


class DowntimeOut(DowntimeIn):
    id: int

    class Config:
        from_attributes = True


# ---------- 场景 ----------
class ScenarioBrief(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""


class ScenarioDetail(ScenarioBrief):
    casters: list[CasterOut]
    ladles: list[LadleOut]
    downtimes: list[DowntimeOut]


class ScenarioConfig(BaseModel):
    """整场景配置：一次提交完成铸机 / 钢包 / 停机区间的覆盖式更新。"""
    casters: list[CasterIn] = Field(default_factory=list)
    ladles: list[LadleIn] = Field(default_factory=list)
    downtimes: list[DowntimeIn] = Field(default_factory=list)


# ---------- 即席模拟 ----------
class AdhocSimulationRequest(ScenarioConfig):
    mode: str = Field("baseline", pattern="^(baseline|optimized)$")


class SimRunOut(BaseModel):
    id: int
    mode: str
    created_at: datetime
    result: dict[str, Any]

    class Config:
        from_attributes = True
