"""排程模拟引擎的核心规则测试。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import engine

BASE = datetime(2026, 9, 18, 8, 0)


def at(minutes: float) -> datetime:
    return BASE + timedelta(minutes=minutes)


def make_ladles(offsets, caster=None, weight=120.0):
    return [
        engine.LadleSpec(seq=i + 1, arrival=at(o), weight_tonnes=weight,
                         caster_id=caster)
        for i, o in enumerate(offsets)
    ]


def make_caster(cycle=45.0, slack=15.0, cap_heats=None, cap_tonnes=None):
    return engine.CasterSpec(
        id="CC1", name="1#连铸机", cycle_minutes=cycle,
        hold_tolerance_minutes=slack, capacity_heats=cap_heats,
        capacity_tonnes=cap_tonnes,
    )


# ---------- 基础衔接 ----------
def test_continuous_casting_no_risk():
    caster = make_caster()
    result = engine.simulate([caster], make_ladles([0, 45, 90], "CC1"), [])
    cr = result["casters"][0]
    assert cr["heats"] == 3
    assert cr["interruptions"] == 0
    assert result["risks"] == []
    assert cr["blocks"][1]["start"] == cr["blocks"][0]["end"]
    assert cr["utilization_pct"] == 100.0


def test_ladle_arrives_early_waits_smoothly():
    # 30 分钟间隔 < 45 分钟周期：第二炉等前炉浇完，仍连浇
    result = engine.simulate([make_caster()], make_ladles([0, 30], "CC1"), [])
    blocks = result["casters"][0]["blocks"]
    assert blocks[1]["start"] == blocks[0]["end"]
    assert blocks[1]["waited_minutes"] == 15.0
    assert result["summary"]["interruptions"] == 0
    assert result["risks"] == []


# ---------- 降速缓冲带 ----------
def test_buffer_zone_baseline_medium_risk():
    # 第一炉 8:00-8:45；第二炉 8:55 到达 => 空闲 10 分钟 ∈ (0,15]：中风险
    result = engine.simulate([make_caster()], make_ladles([0, 55], "CC1"), [])
    risks = result["risks"]
    assert len(risks) == 1
    assert risks[0]["type"] == engine.RISK_LADLE_LATE
    assert risks[0]["severity"] == engine.SEVERITY_MEDIUM
    assert risks[0]["adjust_type"] == engine.ADJUST_HOLD
    assert result["summary"]["interruptions"] == 1


def test_buffer_zone_optimized_slowdown():
    # 优化模式降速衔接：无断浇，产出降速调整建议
    result = engine.simulate(
        [make_caster()], make_ladles([0, 55], "CC1"), [], optimize=True
    )
    cr = result["casters"][0]
    assert cr["interruptions"] == 0
    assert result["risks"] == []
    holds = [a for a in result["adjustments"] if a["type"] == engine.ADJUST_HOLD]
    assert len(holds) == 1
    assert cr["blocks"][1]["used_slowdown"] is True


# ---------- 严重晚到断浇 ----------
def test_severe_late_arrival_high_risk():
    # 第一炉 8:00-8:45；第二炉 10:00 到达 => 空闲 75 分钟 > 15 缓冲
    result = engine.simulate([make_caster()], make_ladles([0, 120], "CC1"), [])
    risks = result["risks"]
    assert len(risks) == 1
    assert risks[0]["severity"] == engine.SEVERITY_HIGH
    assert "75" in risks[0]["message"]
    assert result["summary"]["interruptions"] == 1
    # 断浇后第二炉应在钢包实际到达 10:00 开浇
    assert result["casters"][0]["blocks"][1]["start"] == "2026-09-18T10:00"


def test_severe_late_even_optimizer_cannot_hold():
    result = engine.simulate(
        [make_caster()], make_ladles([0, 120], "CC1"), [], optimize=True
    )
    # 超出降速能力，单铸机无法化解
    assert result["summary"]["high_risks"] == 1


# ---------- 停机冲突 ----------
def test_downtime_conflict_midrun_high_risk():
    downtimes = [engine.DowntimeSpec(
        "CC1", at(60), at(90), reason="结晶器检修"
    )]
    # 第一炉 8:00-8:45，第二炉 8:45 到达 -> 连续浇铸 8:45-9:30 撞停机
    result = engine.simulate([make_caster()], make_ladles([0, 45], "CC1"), downtimes)
    risks = result["risks"]
    assert any(r["type"] == engine.RISK_DOWNTIME_CONFLICT and
               r["severity"] == engine.SEVERITY_HIGH for r in risks)
    block2 = result["casters"][0]["blocks"][1]
    assert block2["start"] == "2026-09-18T09:30"
    assert block2["interrupted_before"] is True


def test_first_heat_during_downtime_is_medium_wait():
    downtimes = [engine.DowntimeSpec("CC1", at(0), at(30))]
    result = engine.simulate([make_caster()], make_ladles([10], "CC1"), downtimes)
    risks = result["risks"]
    assert len(risks) == 1
    assert risks[0]["type"] == engine.RISK_DOWNTIME_CONFLICT
    assert risks[0]["severity"] == engine.SEVERITY_MEDIUM
    assert result["casters"][0]["blocks"][0]["start"] == "2026-09-18T08:30"


# ---------- 优化改派 ----------
def test_optimizer_reassigns_to_avoid_downtime():
    cc1 = make_caster()  # 周期 45，缓冲 15
    cc2 = engine.CasterSpec("CC2", "2#连铸机", 50, 10)
    # CC2 停机 12:30~13:30
    downtimes = [engine.DowntimeSpec("CC2", at(270), at(330), reason="结晶器检修")]
    # CC1 六炉到 11:55（第 6 炉晚 10 分钟）；CC2 五炉到 12:10 浇完
    forced1 = [
        engine.LadleSpec(i, t, caster_id="CC1")
        for i, t in enumerate([at(0), at(45), at(90), at(135), at(180), at(235)], start=1)
    ]
    forced2 = [
        engine.LadleSpec(i, t, caster_id="CC2", weight_tonnes=130)
        for i, t in enumerate([at(0), at(50), at(100), at(150), at(200)], start=7)
    ]
    x = engine.LadleSpec(12, at(260))  # 12:20 到达，不指定铸机
    ladles = forced1 + forced2 + [x]

    # 基准贪心：12:20 时 CC2（12:10 浇完）比 CC1（12:40 浇完）更早空闲 => 分到 CC2 => 撞停机
    base = engine.simulate([cc1, cc2], ladles, downtimes, optimize=False)
    assert any(r["type"] == engine.RISK_DOWNTIME_CONFLICT and r["ladle_seq"] == 12
               for r in base["risks"])

    # 人工钉在 CC2：优化器尊重工艺约束不改派，仍报冲突
    pinned = [l for l in ladles if l.seq != 12] + [
        engine.LadleSpec(12, at(260), caster_id="CC2")
    ]
    opt_pinned = engine.simulate([cc1, cc2], pinned, downtimes, optimize=True)
    assert any(r["type"] == engine.RISK_DOWNTIME_CONFLICT and r["ladle_seq"] == 12
               for r in opt_pinned["risks"])

    # 不指定铸机：优化器改派 CC1（等待 10 分钟连浇），规避停机
    opt = engine.simulate([cc1, cc2], ladles, downtimes, optimize=True)
    assert opt["summary"]["high_risks"] == 0
    cc1_res = next(c for c in opt["casters"] if c["caster_id"] == "CC1")
    assert any(b["ladle_seq"] == 12 for b in cc1_res["blocks"])
    reassigns = [a for a in opt["adjustments"] if a["type"] == engine.ADJUST_REASSIGN]
    assert len(reassigns) == 1
    assert reassigns[0]["from_caster_id"] == "CC2"
    assert reassigns[0]["to_caster_id"] == "CC1"


def test_optimizer_prefers_continuous_over_interrupted():
    cc1 = make_caster()  # 周期 45，缓冲 15
    cc2 = engine.CasterSpec("CC2", "2#连铸机", 50, 10)
    ladles = [
        engine.LadleSpec(1, at(0), caster_id="CC1"),
        engine.LadleSpec(2, at(45), caster_id="CC1"),
        # 9:40 到达：CC1 已 9:30 浇完（空闲 10 分钟，需降速），CC2 完全空闲
        engine.LadleSpec(3, at(100)),
    ]
    opt = engine.simulate([cc1, cc2], ladles, [], optimize=True)
    # 优化器优先选零代价的空闲铸机 CC2，避免降速
    cc1_res = next(c for c in opt["casters"] if c["caster_id"] == "CC1")
    cc2_res = next(c for c in opt["casters"] if c["caster_id"] == "CC2")
    assert cc1_res["heats"] == 2
    assert cc2_res["heats"] == 1
    assert opt["summary"]["interruptions"] == 0


def test_optimizer_uses_slowdown_when_all_casters_busy():
    cc1 = make_caster()  # 缓冲 15
    cc2 = engine.CasterSpec("CC2", "2#连铸机", 50, 10)
    ladles = [
        engine.LadleSpec(1, at(0), caster_id="CC1"),
        engine.LadleSpec(2, at(45), caster_id="CC1"),
        engine.LadleSpec(3, at(0), caster_id="CC2"),
        engine.LadleSpec(4, at(50), caster_id="CC2"),
        # 9:40：CC1 9:30 浇完（空闲 10 ≤ 15 可降速），CC2 9:40 浇完（空闲 0，紧凑）
        engine.LadleSpec(5, at(100)),
    ]
    opt = engine.simulate([cc1, cc2], ladles, [], optimize=True)
    # 两台均不断浇，优先选无需降速、开浇更早的 CC2
    cc2_res = next(c for c in opt["casters"] if c["caster_id"] == "CC2")
    assert cc2_res["heats"] == 3
    assert opt["summary"]["interruptions"] == 0


# ---------- 铸机能力 ----------
def test_capacity_heats_overload():
    caster = make_caster(cap_heats=2)
    result = engine.simulate([caster], make_ladles([0, 45, 90], "CC1"), [])
    overload = [r for r in result["risks"]
                if r["type"] == engine.RISK_CAPACITY_OVERLOAD]
    assert len(overload) == 1
    assert overload[0]["severity"] == engine.SEVERITY_HIGH
    assert "3 炉" in overload[0]["message"]


def test_capacity_tonnes_overload():
    caster = make_caster(cap_tonnes=200.0)
    result = engine.simulate(
        [caster], make_ladles([0, 45], "CC1", weight=120.0), []
    )
    overload = [r for r in result["risks"]
                if r["type"] == engine.RISK_CAPACITY_OVERLOAD]
    assert len(overload) == 1
    assert "240" in overload[0]["message"]


def test_capacity_within_limit_no_risk():
    caster = make_caster(cap_heats=3, cap_tonnes=400.0)
    result = engine.simulate([caster], make_ladles([0, 45, 90], "CC1"), [])
    assert result["risks"] == []


# ---------- 输入校验 ----------
def test_no_caster_raises():
    with pytest.raises(ValueError):
        engine.simulate([], make_ladles([0]), [])


def test_unknown_caster_reference_raises():
    with pytest.raises(ValueError):
        engine.simulate([make_caster()], make_ladles([0], caster="CCX"), [])


def test_invalid_downtime_range_raises():
    with pytest.raises(ValueError):
        engine.simulate(
            [make_caster()], make_ladles([0], "CC1"),
            [engine.DowntimeSpec("CC1", at(60), at(30))],
        )


# ---------- 汇总指标 ----------
def test_summary_metrics():
    cc1 = make_caster()
    result = engine.simulate([cc1], make_ladles([0, 45], "CC1"), [])
    s = result["summary"]
    assert s["total_heats"] == 2
    assert s["total_tonnes"] == 240.0
    assert s["interruptions"] == 0
    assert s["high_risks"] == 0
    assert s["timeline_start"] == "2026-09-18T08:00"
    assert result["mode"] == "baseline"
