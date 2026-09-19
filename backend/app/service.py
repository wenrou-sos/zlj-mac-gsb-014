"""把 ORM 配置 / API 载荷转换为引擎入参并执行模拟。"""
from __future__ import annotations

from app import engine
from app.models import CasterConfig, DowntimeConfig, LadleConfig, Scenario
from app.schemas import ScenarioConfig


def _specs_from_orm(scenario: Scenario):
    casters = [
        engine.CasterSpec(
            id=c.code,
            name=c.name,
            cycle_minutes=c.cycle_minutes,
            hold_tolerance_minutes=c.hold_tolerance_minutes,
            capacity_heats=c.capacity_heats,
            capacity_tonnes=c.capacity_tonnes,
        )
        for c in scenario.casters
    ]
    ladles = [
        engine.LadleSpec(
            seq=l.seq,
            arrival=engine.parse_dt(l.arrival),
            grade=l.grade or "",
            weight_tonnes=l.weight_tonnes,
            caster_id=l.caster_code,
        )
        for l in scenario.ladles
    ]
    downtimes = [
        engine.DowntimeSpec(
            caster_id=d.caster_code,
            start=engine.parse_dt(d.start),
            end=engine.parse_dt(d.end),
            reason=d.reason or "设备维护",
        )
        for d in scenario.downtimes
    ]
    return casters, ladles, downtimes


def run_scenario(scenario: Scenario, optimize: bool) -> dict:
    casters, ladles, downtimes = _specs_from_orm(scenario)
    return engine.simulate(casters, ladles, downtimes, optimize=optimize)


def run_config(config: ScenarioConfig, optimize: bool) -> dict:
    casters = [
        engine.CasterSpec(
            id=c.code, name=c.name, cycle_minutes=c.cycle_minutes,
            hold_tolerance_minutes=c.hold_tolerance_minutes,
            capacity_heats=c.capacity_heats, capacity_tonnes=c.capacity_tonnes,
        )
        for c in config.casters
    ]
    ladles = [
        engine.LadleSpec(
            seq=l.seq, arrival=engine.parse_dt(l.arrival), grade=l.grade,
            weight_tonnes=l.weight_tonnes, caster_id=l.caster_code,
        )
        for l in config.ladles
    ]
    downtimes = [
        engine.DowntimeSpec(
            caster_id=d.caster_code, start=engine.parse_dt(d.start),
            end=engine.parse_dt(d.end), reason=d.reason,
        )
        for d in config.downtimes
    ]
    return engine.simulate(casters, ladles, downtimes, optimize=optimize)
