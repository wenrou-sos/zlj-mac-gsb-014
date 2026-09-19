"""Pydantic request / response schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CasterIn(BaseModel):
    id: str = Field(..., description="铸机编号，如 CC1")
    name: Optional[str] = None
    min_speed: float = Field(0.6, gt=0, description="最低拉速 m/min")
    max_speed: float = Field(2.0, gt=0, description="最高拉速 m/min")
    nominal_speed: float = Field(1.2, gt=0, description="额定拉速 m/min")
    change_duration: int = Field(60, ge=0, description="连浇换包时间 min")
    prep_duration: int = Field(15, ge=0, description="开浇前准备时间 min")
    sequence_max: int = Field(8, ge=1, description="最大连浇炉数")

    @field_validator("max_speed")
    @classmethod
    def _check_speed_window(cls, v, info):
        mn = info.data.get("min_speed")
        if mn is not None and v < mn:
            raise ValueError("max_speed 不能小于 min_speed")
        return v


class LadleIn(BaseModel):
    id: str = Field(..., description="钢包号，如 L1")
    grade: Optional[str] = Field("Q235B", description="钢种")
    arrival: datetime = Field(..., description="到达/可用时刻")
    weight: float = Field(120.0, gt=0, description="钢水重量 t")
    cast_duration: int = Field(45, ge=1, description="浇铸周期(浇铸用时) min")
    caster_id: Optional[str] = Field(None, description="指定铸机；不指定则自动分配")
    priority: int = Field(0, ge=0, description="优先级，数字越大越优先")


class DowntimeIn(BaseModel):
    id: str
    caster_id: str = Field(..., description="停机所属铸机")
    start: datetime
    end: datetime
    reason: Optional[str] = "设备检修"

    @field_validator("end")
    @classmethod
    def _check_end(cls, v, info):
        s = info.data.get("start")
        if s is not None and v <= s:
            raise ValueError("停机结束时间必须晚于开始时间")
        return v


class ScenarioIn(BaseModel):
    name: Optional[str] = "未命名方案"
    casters: List[CasterIn] = Field(default_factory=list)
    ladles: List[LadleIn] = Field(default_factory=list)
    downtimes: List[DowntimeIn] = Field(default_factory=list)

    @field_validator("casters")
    @classmethod
    def _at_least_one_caster(cls, v):
        if not v:
            raise ValueError("至少需要配置一台铸机")
        return v


class SimulationOut(BaseModel):
    id: str
    name: str
    scenario: dict
    result: Optional[dict]
    created_at: datetime


class ScenarioSnapshotOut(BaseModel):
    id: str
    name: str
    payload: dict
    note: Optional[str]
    created_at: datetime
