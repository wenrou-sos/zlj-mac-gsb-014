"""连铸生产节奏模拟引擎。

输入：钢包（炉次）到达计划、铸机浇铸参数、设备停机区间。
输出：逐铸机排程（Gantt 块）、生产节奏指标、断浇风险清单与调整建议。

核心概念
--------
* 浇铸周期 cycle_minutes：一炉钢在该铸机上的纯浇铸时间。
* 降速缓冲 hold_tolerance_minutes：上炉浇完后，铸机靠降速拉坯最多能吸收的
  钢包晚到空隙（分钟）。空隙 = 下炉到达时刻 − 上炉浇完时刻。
* 断浇：晚到空隙 > hold_tolerance_minutes，或浇铸窗口与停机区间直接冲突。

两种模式
--------
* baseline（基准排程）：严格按人工指定铸机排，未指定则"最早空闲铸机"贪心分配，
  只做风险识别与调整建议，不自动改排。
* optimized（优化排程）：自动应用降速缓冲，并把有断浇/停机冲突的炉次改派到
  可连续浇铸的铸机，调整动作在 adjustments 中返回。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# ---------- 风险 / 调整类型常量 ----------
RISK_LADLE_LATE = "ladle_late"                 # 钢包晚到 / 间隔过大导致断浇
RISK_DOWNTIME_CONFLICT = "downtime_conflict"   # 浇铸与设备停机冲突
RISK_CAPACITY_OVERLOAD = "capacity_overload"   # 超出铸机能力

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}

RISK_LABELS = {
    RISK_LADLE_LATE: "断浇风险：钢包晚到",
    RISK_DOWNTIME_CONFLICT: "断浇风险：停机冲突",
    RISK_CAPACITY_OVERLOAD: "产能风险：超出铸机能力",
}

ADJUST_REASSIGN = "reassign"   # 改派其他铸机
ADJUST_HOLD = "hold"           # 降速放缓等待
ADJUST_SHIFT = "shift"         # 提前/推迟开浇
ADJUST_CAPACITY = "capacity"   # 产能调整（分流/延长班时）

ADJUST_LABELS = {
    ADJUST_REASSIGN: "改派铸机",
    ADJUST_HOLD: "降速放缓",
    ADJUST_SHIFT: "调整开浇时间",
    ADJUST_CAPACITY: "产能调整",
}


def parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))


def fmt_dt(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat(timespec="minutes")


def _r(value: float) -> float:
    return round(value + 1e-9, 2)


@dataclass
class Risk:
    type: str
    severity: str
    message: str
    suggestion: str
    adjust_type: str
    ladle_seq: Optional[int] = None
    caster_id: Optional[str] = None
    time: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "type_label": RISK_LABELS[self.type],
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
            "adjust_type": self.adjust_type,
            "adjust_label": ADJUST_LABELS[self.adjust_type],
            "ladle_seq": self.ladle_seq,
            "caster_id": self.caster_id,
            "time": self.time,
        }


@dataclass
class Adjustment:
    """优化模式下实际采取的排程调整动作。"""
    type: str
    description: str
    ladle_seq: Optional[int] = None
    from_caster_id: Optional[str] = None
    to_caster_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "type_label": ADJUST_LABELS[self.type],
            "description": self.description,
            "ladle_seq": self.ladle_seq,
            "from_caster_id": self.from_caster_id,
            "to_caster_id": self.to_caster_id,
        }


@dataclass
class Block:
    ladle_seq: int
    start: datetime
    end: datetime
    arrival: datetime
    weight_tonnes: float
    waited_minutes: float
    gap_from_prev: Optional[float]   # 本炉到达距上炉浇完的分钟数
    interrupted_before: bool        # 该炉开浇前是否发生断浇
    used_slowdown: bool             # 是否使用降速缓冲衔接
    reflowed: bool = False          # 是否为优化改派炉次

    def as_dict(self) -> dict:
        return {
            "ladle_seq": self.ladle_seq,
            "start": fmt_dt(self.start),
            "end": fmt_dt(self.end),
            "arrival": fmt_dt(self.arrival),
            "weight_tonnes": self.weight_tonnes,
            "waited_minutes": _r(self.waited_minutes),
            "gap_from_prev": _r(self.gap_from_prev) if self.gap_from_prev is not None else None,
            "interrupted_before": self.interrupted_before,
            "used_slowdown": self.used_slowdown,
            "reflowed": self.reflowed,
        }


@dataclass
class CasterSpec:
    id: str
    name: str
    cycle_minutes: float
    hold_tolerance_minutes: float = 15.0
    capacity_heats: Optional[int] = None
    capacity_tonnes: Optional[float] = None


@dataclass
class LadleSpec:
    seq: int
    arrival: datetime
    grade: str = ""
    weight_tonnes: float = 120.0
    caster_id: Optional[str] = None   # 人工指定铸机；为空则自动分配


@dataclass
class DowntimeSpec:
    caster_id: str
    start: datetime
    end: datetime
    reason: str = "设备维护"


@dataclass
class _Preview:
    start: datetime
    end: datetime
    gap: Optional[float]
    interrupted: bool
    used_slow: bool
    wait: float
    conflict: Optional[tuple[datetime, datetime]] = None
    first_heat_wait_downtime: bool = False


class _CasterRun:
    """单台铸机的排程状态机。"""

    def __init__(self, spec: CasterSpec, downtimes: list[DowntimeSpec], use_slack: bool):
        self.spec = spec
        self.use_slack = use_slack
        self.downtimes = sorted(
            [(d.start, d.end, d.reason) for d in downtimes if d.caster_id == spec.id]
        )
        self.blocks: list[Block] = []
        self.risks: list[Risk] = []

    @property
    def last_end(self) -> Optional[datetime]:
        return self.blocks[-1].end if self.blocks else None

    def _overlap(self, start: datetime, end: datetime) -> Optional[tuple[datetime, datetime, str]]:
        for ds, de, reason in self.downtimes:
            if start < de and end > ds:
                return ds, de, reason
        return None

    def preview(self, ladle: LadleSpec) -> _Preview:
        """计算把 ladle 排到本铸机的结果，不落库（供优化器比选）。"""
        cycle = timedelta(minutes=self.spec.cycle_minutes)
        slack = timedelta(minutes=self.spec.hold_tolerance_minutes)
        arrival = ladle.arrival

        if not self.blocks:
            start, gap, interrupted, used_slow = arrival, None, False, False
        else:
            prev_end = self.blocks[-1].end
            gap_td = arrival - prev_end
            gap = gap_td.total_seconds() / 60.0
            if gap_td <= timedelta(0):
                # 钢包在上炉浇完前到达：等前炉浇完，紧凑衔接
                start, interrupted, used_slow = prev_end, False, False
            elif gap_td <= slack:
                # 上炉浇完后空闲 gap 分钟（≤缓冲）：优化模式降速衔接，
                # 基准模式不使用缓冲 => 断浇，待钢包到达后重开
                if self.use_slack:
                    start, interrupted, used_slow = prev_end, False, True
                else:
                    start, interrupted, used_slow = arrival, True, False
            else:
                # 超出缓冲能力：断浇，钢包到了再开浇
                start, interrupted, used_slow = arrival, True, False

        wait = max(0.0, (start - arrival).total_seconds() / 60.0)
        conflict = self._overlap(start, start + cycle)
        first_wait = False
        if conflict is not None:
            ds, de, _reason = conflict
            if not self.blocks:
                # 铸机尚未开浇：首炉等停机结束，不算断浇但提示
                start, interrupted, first_wait = de, False, True
            else:
                # 浇铸中途撞停机：跳过停机窗口后重开 => 断浇
                start, interrupted = de, True
            wait = max(0.0, (start - arrival).total_seconds() / 60.0)

        return _Preview(
            start=start, end=start + cycle, gap=gap,
            interrupted=interrupted, used_slow=used_slow,
            wait=wait, conflict=conflict, first_heat_wait_downtime=first_wait,
        )

    def commit(self, ladle: LadleSpec, pv: _Preview, reflowed: bool = False) -> Block:
        block = Block(
            ladle_seq=ladle.seq,
            start=pv.start,
            end=pv.end,
            arrival=ladle.arrival,
            weight_tonnes=ladle.weight_tonnes,
            waited_minutes=pv.wait,
            gap_from_prev=pv.gap,
            interrupted_before=pv.interrupted,
            used_slowdown=pv.used_slow,
            reflowed=reflowed,
        )
        self.blocks.append(block)
        self._emit_risks(ladle, pv)
        return block

    # ---------- 风险识别 ----------
    def _emit_risks(self, ladle: LadleSpec, pv: _Preview) -> None:
        cycle_m = self.spec.cycle_minutes
        slack_m = self.spec.hold_tolerance_minutes
        name = self.spec.name

        if pv.conflict is not None:
            ds, de, reason = pv.conflict
            if pv.first_heat_wait_downtime:
                msg = (
                    f"{name}：首炉（第 {ladle.seq} 炉）到达时正逢停机「{reason}」"
                    f"（{fmt_dt(ds)}~{fmt_dt(de)}），开浇被迫等待至 {fmt_dt(pv.start)}。"
                )
                sug = (
                    f"建议联系炼钢工序将第 {ladle.seq} 炉推迟至 {fmt_dt(de)} 之后调达，"
                    f"或改派至其他在线铸机，避免钢包等待降温。"
                )
                self.risks.append(Risk(
                    RISK_DOWNTIME_CONFLICT, SEVERITY_MEDIUM, msg, sug,
                    ADJUST_SHIFT, ladle.seq, self.spec.id, fmt_dt(ds),
                ))
            else:
                msg = (
                    f"{name}：第 {ladle.seq} 炉浇铸窗口与停机「{reason}」"
                    f"（{fmt_dt(ds)}~{fmt_dt(de)}）冲突，浇铸推迟至 {fmt_dt(pv.start)}，"
                    f"连铸中断。"
                )
                sug = (
                    f"建议将第 {ladle.seq} 炉改派至其他在线铸机；"
                    f"若必须在本机浇铸，需协调设备部门压缩/后移该停机窗口，"
                    f"或提前 {_r(cycle_m)} 分钟于 {fmt_dt(ds)} 前完成本炉开浇。"
                )
                self.risks.append(Risk(
                    RISK_DOWNTIME_CONFLICT, SEVERITY_HIGH, msg, sug,
                    ADJUST_REASSIGN, ladle.seq, self.spec.id, fmt_dt(ds),
                ))
            return

        if pv.gap is not None and pv.interrupted:
            if pv.gap <= slack_m:
                # 基准模式缓冲带断浇：中等风险，降速即可化解
                msg = (
                    f"{name}：第 {ladle.seq} 炉在上炉浇完后 {_r(pv.gap)} 分钟才到达，"
                    f"出现 {_r(pv.gap)} 分钟空隙但仍在降速缓冲（{_r(slack_m)} 分钟）以内，"
                    f"若不降速拉坯将发生断浇。"
                )
                sug = (
                    f"建议对第 {ladle.seq} 炉启动降速拉坯预案"
                    f"（放缓 {_r(pv.gap)} 分钟）保持连浇，"
                    f"或将其提前 {_r(pv.gap)} 分钟调达。"
                )
                self.risks.append(Risk(
                    RISK_LADLE_LATE, SEVERITY_MEDIUM, msg, sug,
                    ADJUST_HOLD, ladle.seq, self.spec.id, fmt_dt(pv.start),
                ))
            else:
                over = _r(pv.gap - slack_m)
                msg = (
                    f"{name}：第 {ladle.seq} 炉在上炉浇完后 {_r(pv.gap)} 分钟才到达，"
                    f"超过降速缓冲能力 {_r(slack_m)} 分钟（超限 {over} 分钟），"
                    f"连铸中断。"
                )
                sug = (
                    f"建议将第 {ladle.seq} 炉提前至少 {over} 分钟调达，"
                    f"或改派至间隔更短的铸机；同时提前做好中包/水口准备，"
                    f"缩短重连时间。"
                )
                self.risks.append(Risk(
                    RISK_LADLE_LATE, SEVERITY_HIGH, msg, sug,
                    ADJUST_REASSIGN, ladle.seq, self.spec.id, fmt_dt(pv.start),
                ))
        elif pv.gap is not None and pv.used_slow and not self.use_slack:
            # 基准模式下缓冲带节奏预警（未发生断浇的情形，保留兜底）
            msg = (
                f"{name}：第 {ladle.seq} 炉在上炉浇完后 {_r(pv.gap)} 分钟才到达，"
                f"处于降速缓冲（{_r(slack_m)} 分钟）以内，节奏偏紧，存在断浇风险。"
            )
            sug = (
                f"建议对第 {ladle.seq} 炉按降速拉坯预案处置，"
                f"或将其提前 {_r(pv.gap)} 分钟调达。"
            )
            self.risks.append(Risk(
                RISK_LADLE_LATE, SEVERITY_MEDIUM, msg, sug,
                ADJUST_HOLD, ladle.seq, self.spec.id, fmt_dt(pv.start),
            ))

    def capacity_risks(self) -> None:
        """全部炉次排定后做铸机能力校核。"""
        heats = len(self.blocks)
        tonnes = _r(sum(b.weight_tonnes for b in self.blocks))
        cap_h = self.spec.capacity_heats
        cap_t = self.spec.capacity_tonnes
        if cap_h is not None and heats > cap_h:
            self.risks.append(Risk(
                RISK_CAPACITY_OVERLOAD, SEVERITY_HIGH,
                f"{self.spec.name}：计划 {heats} 炉，超出铸机炉数能力 {cap_h} 炉。",
                f"建议将至少 {heats - cap_h} 炉分流至其他铸机，或延长/增加浇铸班次。",
                ADJUST_CAPACITY, None, self.spec.id,
                fmt_dt(self.blocks[cap_h].start) if cap_h < len(self.blocks) else None,
            ))
        if cap_t is not None and tonnes > cap_t:
            self.risks.append(Risk(
                RISK_CAPACITY_OVERLOAD, SEVERITY_HIGH,
                f"{self.spec.name}：计划产量 {tonnes} 吨，超出铸机吨位能力 {_r(cap_t)} 吨。",
                f"建议分流约 {_r(tonnes - cap_t)} 吨产量至其他铸机，或协调提高铸机作业班次。",
                ADJUST_CAPACITY, None, self.spec.id,
            ))


# ---------- 顶层调度 ----------
def _baseline_greedy(runs: dict[str, _CasterRun]) -> str:
    """基准模式：选最早空闲铸机。"""
    return min(
        runs.values(),
        key=lambda r: (r.last_end or datetime.max, r.spec.id),
    ).spec.id


def _optimized_choose(runs: dict[str, _CasterRun], ladle: LadleSpec) -> tuple[str, _Preview]:
    """优化模式：逐铸机预览，按代价最小选择。

    代价优先级：不断浇且无停机冲突 > 仅用降速缓冲 > 首炉等停机 >
    断浇/停机冲突 > 开浇时间更晚。
    """
    candidates: list[tuple[int, int, datetime, str, _Preview]] = []
    for cid, run in runs.items():
        pv = run.preview(ladle)
        if pv.conflict is not None and not pv.first_heat_wait_downtime:
            penalty = 4
        elif pv.interrupted:
            penalty = 3
        elif pv.first_heat_wait_downtime:
            penalty = 2
        elif pv.used_slow:
            penalty = 1
        else:
            penalty = 0
        # 已超能力的铸机额外惩罚
        cap_h = run.spec.capacity_heats
        if cap_h is not None and len(run.blocks) >= cap_h:
            penalty += 2
        candidates.append((penalty, len(run.blocks), pv.start, cid, pv))
    _, _, _, cid, pv = min(candidates, key=lambda x: (x[0], x[2], x[3]))
    return cid, pv


def _baseline_assignment(
    casters: list[CasterSpec], ladles: list[LadleSpec], downtimes: list[DowntimeSpec]
) -> dict[int, str]:
    """基准贪心排程：只跑状态机不收集风险，返回 {炉次序号: 铸机id}。"""
    runs = {c.id: _CasterRun(c, downtimes, use_slack=False) for c in casters}
    assignment: dict[int, str] = {}
    for ladle in sorted(ladles, key=lambda l: (l.arrival, l.seq)):
        if ladle.caster_id:
            cid = ladle.caster_id
        else:
            cid = _baseline_greedy(runs)
        pv = runs[cid].preview(ladle)
        runs[cid].commit(ladle, pv)
        assignment[ladle.seq] = cid
    return assignment


def simulate(
    casters: list[CasterSpec],
    ladles: list[LadleSpec],
    downtimes: list[DowntimeSpec],
    optimize: bool = False,
) -> dict:
    """执行模拟并返回可 JSON 序列化的结果。"""
    if not casters:
        raise ValueError("至少需要配置一台铸机")
    caster_ids = {c.id for c in casters}
    missing = {l.caster_id for l in ladles if l.caster_id} - caster_ids
    if missing:
        raise ValueError(f"钢包指定了不存在的铸机：{sorted(missing)}")
    for d in downtimes:
        if d.caster_id not in caster_ids:
            raise ValueError(f"停机区间指定了不存在的铸机：{d.caster_id}")
        if d.end <= d.start:
            raise ValueError("停机区间结束时间必须晚于开始时间")

    runs = {c.id: _CasterRun(c, downtimes, use_slack=optimize) for c in casters}
    name_by_id = {c.id: c.name for c in casters}
    adjustments: list[Adjustment] = []
    baseline_map = (
        _baseline_assignment(casters, ladles, downtimes) if optimize else {}
    )

    for ladle in sorted(ladles, key=lambda l: (l.arrival, l.seq)):
        baseline_cid = (
            ladle.caster_id
            or (baseline_map.get(ladle.seq) if optimize else None)
        )

        reflowed = False
        if optimize and ladle.caster_id is None:
            cid, pv = _optimized_choose(runs, ladle)
            if baseline_cid and cid != baseline_cid:
                reflowed = True
        else:
            cid = ladle.caster_id or _baseline_greedy(runs)
            pv = runs[cid].preview(ladle)

        run = runs[cid]
        run.commit(ladle, pv, reflowed=reflowed)

        # 记录优化动作
        if reflowed:
            avoided = not (pv.interrupted or pv.conflict)
            adjustments.append(Adjustment(
                ADJUST_REASSIGN,
                f"第 {ladle.seq} 炉由 {name_by_id[baseline_cid]} 改派至 {run.spec.name}"
                f"（{'避免断浇' if avoided else '降低断浇/停机冲突影响'}）",
                ladle.seq, baseline_cid, cid,
            ))
        if pv.used_slow:
            adjustments.append(Adjustment(
                ADJUST_HOLD,
                f"{run.spec.name}：第 {ladle.seq} 炉在上炉浇完后 {_r(pv.gap)} 分钟才到达，"
                f"按降速拉坯预案放缓 {_r(pv.gap or 0)} 分钟衔接，未断浇。",
                ladle.seq, cid, cid,
            ))

    for run in runs.values():
        run.capacity_risks()

    return _build_result(runs, downtimes, adjustments, optimize)


def _build_result(
    runs: dict[str, _CasterRun],
    downtimes: list[DowntimeSpec],
    adjustments: list[Adjustment],
    optimize: bool,
) -> dict:
    risks: list[Risk] = []
    caster_results = []
    all_starts: list[datetime] = [d.start for d in downtimes]
    all_ends: list[datetime] = [d.end for d in downtimes]

    for cid, run in sorted(runs.items()):
        risks.extend(run.risks)
        blocks = run.blocks
        if blocks:
            all_starts += [b.start for b in blocks]
            all_ends += [b.end for b in blocks]
            span = (blocks[-1].end - blocks[0].start).total_seconds() / 60.0
            casting = sum(
                (b.end - b.start).total_seconds() / 60.0 for b in blocks
            )
            util = _r(casting / span * 100) if span > 0 else 0.0
            idle = _r(span - casting)
        else:
            util, idle = 0.0, 0.0

        caster_results.append({
            "caster_id": cid,
            "name": run.spec.name,
            "cycle_minutes": run.spec.cycle_minutes,
            "hold_tolerance_minutes": run.spec.hold_tolerance_minutes,
            "capacity_heats": run.spec.capacity_heats,
            "capacity_tonnes": run.spec.capacity_tonnes,
            "heats": len(blocks),
            "tonnes": _r(sum(b.weight_tonnes for b in blocks)),
            "start": fmt_dt(blocks[0].start) if blocks else None,
            "end": fmt_dt(blocks[-1].end) if blocks else None,
            "utilization_pct": util,
            "idle_minutes": idle,
            "interruptions": sum(1 for b in blocks if b.interrupted_before),
            "slowdowns": sum(1 for b in blocks if b.used_slowdown),
            "total_waited_minutes": _r(sum(b.waited_minutes for b in blocks)),
            "blocks": [b.as_dict() for b in blocks],
            "downtimes": [
                {"start": fmt_dt(ds), "end": fmt_dt(de), "reason": reason}
                for ds, de, reason in run.downtimes
            ],
        })

    risks.sort(key=lambda r: (SEVERITY_ORDER[r.severity], r.time or ""))
    total_heats = sum(len(r.blocks) for r in runs.values())
    total_interruptions = sum(
        1 for r in runs.values() for b in r.blocks if b.interrupted_before
    )

    result = {
        "mode": "optimized" if optimize else "baseline",
        "casters": caster_results,
        "risks": [r.as_dict() for r in risks],
        "adjustments": [a.as_dict() for a in adjustments],
        "summary": {
            "total_heats": total_heats,
            "total_tonnes": _r(sum(
                b.weight_tonnes for r in runs.values() for b in r.blocks
            )),
            "total_casters": len(runs),
            "interruptions": total_interruptions,
            "high_risks": sum(1 for r in risks if r.severity == SEVERITY_HIGH),
            "medium_risks": sum(1 for r in risks if r.severity == SEVERITY_MEDIUM),
            "low_risks": sum(1 for r in risks if r.severity == SEVERITY_LOW),
            "adjustments_applied": len(adjustments),
            "timeline_start": fmt_dt(min(all_starts)) if all_starts else None,
            "timeline_end": fmt_dt(max(all_ends)) if all_ends else None,
        },
    }
    return result
