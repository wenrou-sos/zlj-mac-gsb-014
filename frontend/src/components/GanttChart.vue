<template>
  <div class="gantt">
    <div class="gantt-scroll">
      <div class="gantt-inner" :style="{ width: leftWidth + laneWidth + 'px' }">
        <!-- 时间刻度 -->
        <div class="ruler" :style="{ marginLeft: leftWidth + 'px' }">
          <div
            v-for="t in ticks" :key="t.iso"
            class="tick"
            :style="{ left: x(t.ms) + 'px' }"
          >
            <span class="tick-label">{{ t.label }}</span>
            <span class="tick-line"></span>
          </div>
        </div>

        <!-- 每台铸机一行 -->
        <div v-for="c in result.casters" :key="c.caster_id" class="lane-row">
          <div class="lane-label" :style="{ width: leftWidth + 'px' }">
            <div class="lane-name">{{ c.name }}</div>
            <div class="lane-meta">{{ c.heats }}炉 · {{ c.tonnes }}t · 利用{{ c.utilization_pct }}%</div>
          </div>
          <div class="lane" :style="{ width: laneWidth + 'px' }">
            <div class="grid">
              <div
                v-for="t in ticks" :key="t.iso"
                class="grid-line"
                :style="{ left: x(t.ms) + 'px' }"
              ></div>
            </div>

            <!-- 停机区间 -->
            <div
              v-for="(d, i) in c.downtimes" :key="'d' + i"
              class="downtime"
              :style="blockStyle(d.start, d.end)"
            >
              <span class="downtime-text">⛔ {{ d.reason }}</span>
            </div>

            <!-- 浇铸块 -->
            <div
              v-for="b in c.blocks" :key="b.ladle_seq"
              class="heat"
              :class="heatClass(b)"
              :style="blockStyle(b.start, b.end)"
              :title="tip(c, b)"
            >
              <span v-if="blockPx(b.start, b.end) > 34" class="heat-text">#{{ b.ladle_seq }}</span>
              <span v-if="b.interrupted_before" class="break-mark" :style="breakMarkStyle(b)">✖</span>
            </div>

            <!-- 到达时刻标记（钢包到达但未开浇的等待可视化） -->
            <template v-for="b in c.blocks" :key="'a' + b.ladle_seq">
              <div
                v-if="Math.abs(new Date(b.arrival) - new Date(b.start)) > 30000"
                class="arrival"
                :style="{ left: x(new Date(b.arrival)) + 'px' }"
                :title="`第${b.ladle_seq}炉 ${b.arrival.slice(11, 16)} 到达`"
              >▼</div>
            </template>
          </div>
        </div>
      </div>
    </div>
    <div class="legend">
      <span><i class="lg ok"></i>正常连浇</span>
      <span><i class="lg slow"></i>降速衔接</span>
      <span><i class="lg break"></i>断浇后重开</span>
      <span><i class="lg reflow"></i>优化改派</span>
      <span><i class="lg down"></i>停机区间</span>
      <span><i class="lg arr"></i>▼ 钢包到达</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
})

const leftWidth = 132
const laneWidth = 1080
const HOUR_PX = 110

const range = computed(() => {
  const s = props.result.summary
  const start = new Date(s.timeline_start).getTime()
  let end = new Date(s.timeline_end).getTime()
  // 保证刻度至少 7 小时，视觉更稳定
  if (end - start < 7 * 3600_000) end = start + 7 * 3600_000
  return { start, end }
})

const ticks = computed(() => {
  const out = []
  const t = new Date(range.value.start)
  t.setMinutes(0, 0, 0)
  while (t.getTime() <= range.value.end) {
    out.push({
      ms: t.getTime(),
      iso: t.toISOString(),
      label: `${String(t.getHours()).padStart(2, '0')}:00`,
    })
    t.setHours(t.getHours() + 1)
  }
  return out
})

function x(ms) {
  const t = typeof ms === 'number' ? ms : new Date(ms).getTime()
  return (t - range.value.start) / 3600_000 * HOUR_PX
}

function blockPx(start, end) {
  return (new Date(end) - new Date(start)) / 3600_000 * HOUR_PX
}

function blockStyle(start, end) {
  return {
    left: x(start) + 'px',
    width: Math.max(blockPx(start, end), 3) + 'px',
  }
}

function breakMarkStyle(b) {
  return { left: '-9px' }
}

function heatClass(b) {
  if (b.reflowed) return 'reflow'
  if (b.interrupted_before) return 'break'
  if (b.used_slowdown) return 'slow'
  return 'ok'
}

function tip(c, b) {
  const lines = [
    `第 ${b.ladle_seq} 炉（${c.name}）`,
    `到达 ${b.arrival.slice(11, 16)}`,
    `浇铸 ${b.start.slice(11, 16)} ~ ${b.end.slice(11, 16)}`,
    `等待 ${b.waited_minutes} 分钟 · ${b.weight_tonnes}t`,
  ]
  if (b.used_slowdown) lines.push('降速拉坯衔接')
  if (b.interrupted_before) lines.push('开浇前发生断浇')
  if (b.reflowed) lines.push('优化改派炉次')
  return lines.join('\n')
}
</script>

<style scoped>
.gantt-scroll { overflow-x: auto; }
.gantt-inner { min-width: 100%; }

.ruler {
  position: relative;
  height: 24px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.tick { position: absolute; top: 0; bottom: 0; }
.tick-label {
  position: absolute;
  left: 4px;
  top: 2px;
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}
.tick-line {
  position: absolute;
  left: 0;
  top: 18px;
  width: 1px;
  height: 6px;
  background: var(--border);
}

.lane-row { display: flex; align-items: center; margin-bottom: 6px; }
.lane-label { flex: none; padding-right: 12px; text-align: right; }
.lane-name { font-size: 13px; font-weight: 600; }
.lane-meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

.lane {
  position: relative;
  flex: none;
  height: 38px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.grid-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #1c2530;
}

.heat {
  position: absolute;
  top: 7px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 3px;
  box-shadow: inset 0 -2px 0 rgba(0,0,0,.25);
}
.heat.ok { background: linear-gradient(180deg, #2f9e5e, #22834d); }
.heat.slow { background: linear-gradient(180deg, #d9922a, #c07a1c); }
.heat.break { background: linear-gradient(180deg, #dc4b4b, #b73838); }
.heat.reflow { background: linear-gradient(180deg, #8b6ff0, #7355d8); }
.heat-text { font-size: 11px; font-weight: 700; color: rgba(255,255,255,.95); }
.break-mark {
  position: absolute;
  top: -7px;
  font-size: 12px;
  color: var(--red);
  font-weight: 900;
  text-shadow: 0 0 4px #000;
}

.downtime {
  position: absolute;
  top: 3px;
  height: 32px;
  background: repeating-linear-gradient(
    45deg, rgba(239,68,68,.16), rgba(239,68,68,.16) 6px,
    rgba(239,68,68,.06) 6px, rgba(239,68,68,.06) 12px
  );
  border: 1px dashed rgba(239,68,68,.55);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.downtime-text { font-size: 10.5px; color: #fca5a5; white-space: nowrap; }

.arrival {
  position: absolute;
  top: -15px;
  font-size: 10px;
  color: var(--cyan);
  transform: translateX(-50%);
}

.legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-dim);
}
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.lg { width: 14px; height: 10px; border-radius: 3px; display: inline-block; }
.lg.ok { background: #22834d; }
.lg.slow { background: #c07a1c; }
.lg.break { background: #b73838; }
.lg.reflow { background: #7355d8; }
.lg.down {
  background: repeating-linear-gradient(45deg, rgba(239,68,68,.4) 0 3px, transparent 3px 6px);
  border: 1px dashed rgba(239,68,68,.6);
}
.lg.arr { background: none; color: var(--cyan); font-size: 11px; width: auto; height: auto; }
</style>
