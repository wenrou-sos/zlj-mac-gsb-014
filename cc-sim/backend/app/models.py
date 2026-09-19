"""Database models.

A simulation run stores the full scenario (casters / ladles / downtimes) together
with the computed result as JSON, so historical runs can be listed and revisited
without re-running the engine.
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, String, Text

from .database import Base


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(String(32), primary_key=True, default=_new_id)
    name = Column(String(255), nullable=False, default="未命名方案")
    scenario = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ScenarioSnapshot(Base):
    """A named scenario template that can be loaded back into the editor."""

    __tablename__ = "scenario_snapshots"

    id = Column(String(32), primary_key=True, default=_new_id)
    name = Column(String(255), nullable=False, default="未命名场景")
    payload = Column(JSON, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
