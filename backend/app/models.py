"""SQLAlchemy ORM 模型：场景配置与其下的铸机 / 钢包 / 停机区间。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    casters: Mapped[list["CasterConfig"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="CasterConfig.id",
    )
    ladles: Mapped[list["LadleConfig"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="LadleConfig.arrival",
    )
    downtimes: Mapped[list["DowntimeConfig"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="DowntimeConfig.start",
    )
    runs: Mapped[list["SimRun"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="SimRun.id.desc()",
    )


class CasterConfig(Base):
    __tablename__ = "casters"
    __table_args__ = (UniqueConstraint("scenario_id", "code", name="uq_caster_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cycle_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    hold_tolerance_minutes: Mapped[float] = mapped_column(Float, default=15.0)
    capacity_heats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_tonnes: Mapped[float | None] = mapped_column(Float, nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="casters")


class LadleConfig(Base):
    __tablename__ = "ladles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    grade: Mapped[str] = mapped_column(String(64), default="")
    weight_tonnes: Mapped[float] = mapped_column(Float, default=120.0)
    caster_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="ladles")


class DowntimeConfig(Base):
    __tablename__ = "downtimes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    caster_code: Mapped[str] = mapped_column(String(32), nullable=False)
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), default="设备维护")

    scenario: Mapped[Scenario] = relationship(back_populates="downtimes")


class SimRun(Base):
    __tablename__ = "sim_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(16), default="baseline")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="runs")
