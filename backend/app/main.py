"""FastAPI 入口：场景配置 CRUD、模拟执行、演示数据。"""
from __future__ import annotations

from datetime import datetime, timedelta

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import service
from app.database import get_db, init_db
from app.models import CasterConfig, DowntimeConfig, LadleConfig, Scenario, SimRun
from app.schemas import (
    AdhocSimulationRequest,
    ScenarioBrief,
    ScenarioConfig,
    ScenarioCreate,
    ScenarioDetail,
    SimRunOut,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="连铸生产节奏模拟平台 API",
    description="配置钢包到达、浇铸周期、铸机能力与停机区间，识别断浇风险并给出排程调整建议。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------- 场景 ----------
@app.get("/api/scenarios", response_model=list[ScenarioBrief])
def list_scenarios(db: Session = Depends(get_db)):
    return db.scalars(select(Scenario).order_by(Scenario.id.desc())).all()


@app.post("/api/scenarios", response_model=ScenarioDetail, status_code=201)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Scenario).where(Scenario.name == payload.name)):
        raise HTTPException(409, f"场景名称已存在：{payload.name}")
    scenario = Scenario(name=payload.name, description=payload.description)
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return _load_detail(db, scenario.id)


@app.get("/api/scenarios/{scenario_id}", response_model=ScenarioDetail)
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    return _load_detail(db, scenario_id)


@app.put("/api/scenarios/{scenario_id}/config", response_model=ScenarioDetail)
def update_scenario_config(
    scenario_id: int, payload: ScenarioConfig, db: Session = Depends(get_db)
):
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "场景不存在")

    codes = [c.code for c in payload.casters]
    if len(codes) != len(set(codes)):
        raise HTTPException(422, "铸机编号存在重复")
    code_set = set(codes)
    bad_ladle = {l.caster_code for l in payload.ladles if l.caster_code} - code_set
    if bad_ladle:
        raise HTTPException(422, f"钢包指定了不存在的铸机：{sorted(bad_ladle)}")
    bad_dt = {d.caster_code for d in payload.downtimes} - code_set
    if bad_dt:
        raise HTTPException(422, f"停机区间指定了不存在的铸机：{sorted(bad_dt)}")
    seqs = [l.seq for l in payload.ladles]
    if len(seqs) != len(set(seqs)):
        raise HTTPException(422, "炉次序号存在重复")

    # 覆盖式更新
    db.query(CasterConfig).filter_by(scenario_id=scenario_id).delete()
    db.query(LadleConfig).filter_by(scenario_id=scenario_id).delete()
    db.query(DowntimeConfig).filter_by(scenario_id=scenario_id).delete()
    db.add_all([
        CasterConfig(scenario_id=scenario_id, **c.model_dump()) for c in payload.casters
    ])
    db.add_all([
        LadleConfig(scenario_id=scenario_id, **l.model_dump()) for l in payload.ladles
    ])
    db.add_all([
        DowntimeConfig(scenario_id=scenario_id, **d.model_dump())
        for d in payload.downtimes
    ])
    db.commit()
    return _load_detail(db, scenario_id)


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)):
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(404, "场景不存在")
    db.delete(scenario)
    db.commit()


# ---------- 模拟 ----------
@app.post("/api/scenarios/{scenario_id}/simulate", response_model=SimRunOut, status_code=201)
def simulate_scenario(
    scenario_id: int,
    mode: str = Query("baseline", pattern="^(baseline|optimized)$"),
    persist: bool = Query(True),
    db: Session = Depends(get_db),
):
    scenario = _load_detail(db, scenario_id)
    if not scenario.casters:
        raise HTTPException(422, "请先为场景配置至少一台铸机")
    try:
        result = service.run_scenario(scenario, optimize=(mode == "optimized"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    run = None
    if persist:
        run = SimRun(scenario_id=scenario_id, mode=mode, result=result)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    return SimRun(id=0, mode=mode, created_at=datetime.utcnow(), result=result)


@app.get("/api/scenarios/{scenario_id}/runs", response_model=list[SimRunOut])
def list_runs(scenario_id: int, db: Session = Depends(get_db)):
    if db.get(Scenario, scenario_id) is None:
        raise HTTPException(404, "场景不存在")
    return db.scalars(
        select(SimRun).where(SimRun.scenario_id == scenario_id).order_by(SimRun.id.desc())
    ).all()


@app.post("/api/simulate")
def simulate_adhoc(payload: AdhocSimulationRequest):
    """不入库的即席模拟，供前端快速试算。"""
    if not payload.casters:
        raise HTTPException(422, "至少需要配置一台铸机")
    try:
        return service.run_config(payload, optimize=(payload.mode == "optimized"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ---------- 演示数据 ----------
@app.post("/api/seed", response_model=ScenarioDetail, status_code=201)
def seed_demo(db: Session = Depends(get_db)):
    """写入一套典型白班排程演示数据（含缓冲带炉次与停机冲突炉次）。"""
    name = "演示：两机两流白班排程"
    existing = db.scalar(select(Scenario).where(Scenario.name == name))
    if existing is not None:
        return _load_detail(db, existing.id)

    scenario = Scenario(name=name, description="1#/2# 连铸机白班计划，含设备停机与晚到炉次")
    db.add(scenario)
    db.flush()

    base = datetime(2026, 9, 18, 8, 0)
    casters = [
        CasterConfig(scenario_id=scenario.id, code="CC1", name="1#连铸机",
                     cycle_minutes=45, hold_tolerance_minutes=15,
                     capacity_heats=10, capacity_tonnes=1200),
        CasterConfig(scenario_id=scenario.id, code="CC2", name="2#连铸机",
                     cycle_minutes=50, hold_tolerance_minutes=10,
                     capacity_heats=8, capacity_tonnes=960),
    ]
    db.add_all(casters)

    # CC1（周期 45，缓冲 15）：8:00 起连续 5 炉，第 6 炉 11:55 到达
    #   => 距上炉浇完空闲 10 分钟，落入降速缓冲带（基准中风险，优化降速化解）。
    cc1_times = [0, 45, 90, 135, 180, 235]
    # CC2（周期 50，缓冲 10）：8:00 起连续 5 炉浇到 12:10；
    #   12:30~13:30 结晶器检修。
    cc2_times = [0, 50, 100, 150, 200]
    # 12:20 到达的一炉不指定铸机：基准贪心选更早空闲的 CC2 => 撞停机（高风险）；
    # 优化模式改派 CC1 规避。
    cc2_auto_times = [260]

    ladles: list[LadleConfig] = []
    seq = 1
    for off in cc1_times:
        ladles.append(LadleConfig(
            scenario_id=scenario.id, seq=seq, arrival=base + timedelta(minutes=off),
            grade="Q235B", weight_tonnes=120, caster_code="CC1",
        ))
        seq += 1
    for off in cc2_times:
        ladles.append(LadleConfig(
            scenario_id=scenario.id, seq=seq, arrival=base + timedelta(minutes=off),
            grade="HRB400", weight_tonnes=130, caster_code="CC2",
        ))
        seq += 1
    for off in cc2_auto_times:
        ladles.append(LadleConfig(
            scenario_id=scenario.id, seq=seq, arrival=base + timedelta(minutes=off),
            grade="HRB400", weight_tonnes=130, caster_code=None,
        ))
        seq += 1
    db.add_all(ladles)

    db.add(DowntimeConfig(
        scenario_id=scenario.id, caster_code="CC2",
        start=datetime(2026, 9, 18, 12, 30),
        end=datetime(2026, 9, 18, 13, 30),
        reason="结晶器检修",
    ))
    db.commit()
    return _load_detail(db, scenario.id)


def _load_detail(db: Session, scenario_id: int) -> Scenario:
    scenario = db.scalar(
        select(Scenario)
        .where(Scenario.id == scenario_id)
        .options(
            selectinload(Scenario.casters),
            selectinload(Scenario.ladles),
            selectinload(Scenario.downtimes),
        )
    )
    if scenario is None:
        raise HTTPException(404, "场景不存在")
    return scenario
