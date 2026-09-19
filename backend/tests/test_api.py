"""API 端到端测试（SQLite + TestClient）。"""
from __future__ import annotations

import os
import tempfile

import pytest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import engine as db_engine  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402


@pytest.fixture(scope="module")
def client():
    models.Base.metadata.drop_all(bind=db_engine)
    models.Base.metadata.create_all(bind=db_engine)
    with TestClient(app) as c:
        yield c


def _find_scenario(client, name: str) -> int:
    rows = client.get("/api/scenarios").json()
    return next(s["id"] for s in rows if s["name"] == name)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scenario_crud_and_config(client):
    r = client.post("/api/scenarios", json={"name": "测试场景", "description": "单测"})
    assert r.status_code == 201
    sid = r.json()["id"]

    r = client.get(f"/api/scenarios/{sid}")
    assert r.status_code == 200
    assert r.json()["casters"] == []

    config = {
        "casters": [{
            "code": "CC1", "name": "1#连铸机", "cycle_minutes": 45,
            "hold_tolerance_minutes": 15, "capacity_heats": 10,
            "capacity_tonnes": 1200,
        }],
        "ladles": [
            {"seq": 1, "arrival": "2026-09-18T08:00", "weight_tonnes": 120,
             "caster_code": "CC1"},
            {"seq": 2, "arrival": "2026-09-18T09:30", "weight_tonnes": 120,
             "caster_code": "CC1"},
        ],
        "downtimes": [],
    }
    r = client.put(f"/api/scenarios/{sid}/config", json=config)
    assert r.status_code == 200
    assert len(r.json()["casters"]) == 1
    assert len(r.json()["ladles"]) == 2

    # 重复炉次号应被拒绝
    bad = {**config, "ladles": config["ladles"] * 2}
    r = client.put(f"/api/scenarios/{sid}/config", json=bad)
    assert r.status_code == 422

    # 引用不存在的铸机应被拒绝
    bad = {**config, "ladles": [
        {**config["ladles"][0], "caster_code": "CCX"}
    ]}
    r = client.put(f"/api/scenarios/{sid}/config", json=bad)
    assert r.status_code == 422


def test_simulate_baseline_and_optimized(client):
    sid = _find_scenario(client, "测试场景")
    r = client.post(f"/api/scenarios/{sid}/simulate?mode=baseline")
    assert r.status_code == 201
    body = r.json()
    assert body["mode"] == "baseline"
    assert body["id"] > 0
    # 第二炉间隔 90 分钟 > 45+15，高风险断浇
    assert body["result"]["summary"]["high_risks"] == 1
    assert body["result"]["risks"][0]["type"] == "ladle_late"
    assert "改派" in body["result"]["risks"][0]["suggestion"]

    r = client.post(f"/api/scenarios/{sid}/simulate?mode=optimized")
    assert r.status_code == 201
    # 单铸机无法化解严重晚到，但结果结构完整
    assert r.json()["result"]["summary"]["high_risks"] == 1

    r = client.get(f"/api/scenarios/{sid}/runs")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_adhoc_simulation(client):
    payload = {
        "mode": "optimized",
        "casters": [
            {"code": "CC1", "name": "1#机", "cycle_minutes": 45,
             "hold_tolerance_minutes": 15},
            {"code": "CC2", "name": "2#机", "cycle_minutes": 50,
             "hold_tolerance_minutes": 10},
        ],
        "ladles": [
            {"seq": 1, "arrival": "2026-09-18T08:00", "caster_code": "CC1"},
            {"seq": 2, "arrival": "2026-09-18T08:55", "caster_code": "CC1"},
        ],
        "downtimes": [],
    }
    r = client.post("/api/simulate", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "optimized"
    # 间隔 55 ∈ (45,60]：优化器降速衔接
    assert data["summary"]["interruptions"] == 0
    assert any(a["type"] == "hold" for a in data["adjustments"])


def test_adhoc_validation_error(client):
    r = client.post("/api/simulate", json={
        "casters": [], "ladles": [], "downtimes": [], "mode": "baseline",
    })
    assert r.status_code == 422


def test_seed_demo(client):
    r = client.post("/api/seed")
    assert r.status_code == 201
    data = r.json()
    assert len(data["casters"]) == 2
    assert len(data["ladles"]) == 12
    assert len(data["downtimes"]) == 1
    sid = data["id"]

    base = client.post(f"/api/scenarios/{sid}/simulate?mode=baseline").json()
    risks = {(r["type"], r["severity"]) for r in base["result"]["risks"]}
    assert ("ladle_late", "medium") in risks       # CC1 缓冲带炉次
    assert ("downtime_conflict", "high") in risks   # CC2 停机冲突炉次

    opt = client.post(
        f"/api/scenarios/{sid}/simulate?mode=optimized"
    ).json()["result"]
    # 优化改派 + 降速后无高风险
    assert opt["summary"]["high_risks"] == 0
    assert opt["summary"]["adjustments_applied"] >= 2
    types = {a["type"] for a in opt["adjustments"]}
    assert "reassign" in types
    assert "hold" in types


def test_seed_idempotent(client):
    r1 = client.post("/api/seed")
    r2 = client.post("/api/seed")
    assert r1.json()["id"] == r2.json()["id"]


def test_delete_scenario(client):
    sid = client.post("/api/scenarios", json={"name": "待删除"}).json()["id"]
    r = client.delete(f"/api/scenarios/{sid}")
    assert r.status_code == 204
    assert client.get(f"/api/scenarios/{sid}").status_code == 404
