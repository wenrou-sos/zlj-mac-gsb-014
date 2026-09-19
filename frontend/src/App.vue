<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">🏗️</span>
        <div>
          <h1>连铸生产节奏模拟平台</h1>
          <p>Continuous Casting Rhythm Simulator · 钢包节奏 / 断浇风险识别 / 排程优化建议</p>
        </div>
      </div>
      <div class="top-actions">
        <select v-model="currentId" class="scenario-select" @change="onScenarioChange">
          <option v-for="s in scenarios" :key="s.id" :value="s.id">
            {{ s.name }}
          </option>
        </select>
        <button @click="createScenario" :disabled="busy">＋ 新场景</button>
        <button @click="seedDemo" :disabled="busy">🎯 载入演示数据</button>
        <button class="danger" @click="removeScenario" :disabled="!currentId || busy">删除</button>
        <span class="api-state" :class="apiOk ? 'ok' : 'bad'">
          ● {{ apiOk ? 'API 已连接' : 'API 未连接' }}
        </span>
      </div>
    </header>

    <div v-if="toast" class="toast" :class="{ ok: toastOk }">{{ toast }}</div>

    <main class="main">
      <!-- 左：配置 -->
      <div class="col left">
        <div class="panel" v-if="config">
          <h2>⚙️ 生产配置</h2>
          <ConfigEditor
            :model-value="config"
            :busy="busy"
            @save="saveAndSimulate"
            @reset="loadScenario"
          />
        </div>
      </div>

      <!-- 右：模拟结果 -->
      <div class="col right">
        <div class="panel run-bar">
          <div class="mode-switch">
            <button
              :class="{ primary: mode === 'baseline' }"
              @click="runSimulation('baseline')" :disabled="busy"
            >▶ 基准排程（风险识别）</button>
            <button
              :class="{ primary: mode === 'optimized' }"
              @click="runSimulation('optimized')" :disabled="busy"
            >⚡ 优化排程（自动调整）</button>
          </div>
          <button class="ghost sm" @click="loadRuns" :disabled="!currentId">历史结果</button>
        </div>

        <template v-if="result">
          <!-- 指标卡 -->
          <div class="stats">
            <div class="stat">
              <div class="stat-v">{{ result.summary.total_heats }}</div>
              <div class="stat-k">总炉数</div>
            </div>
            <div class="stat">
              <div class="stat-v">{{ result.summary.total_tonnes }}<small>t</small></div>
              <div class="stat-k">总吨位</div>
            </div>
            <div class="stat" :class="{ bad: result.summary.interruptions }">
              <div class="stat-v">{{ result.summary.interruptions }}</div>
              <div class="stat-k">断浇次数</div>
            </div>
            <div class="stat" :class="{ bad: result.summary.high_risks }">
              <div class="stat-v">{{ result.summary.high_risks }}</div>
              <div class="stat-k">高风险</div>
            </div>
            <div class="stat">
              <div class="stat-v">{{ result.summary.medium_risks }}</div>
              <div class="stat-k">中风险</div>
            </div>
            <div class="stat">
              <div class="stat-v">{{ result.summary.adjustments_applied }}</div>
              <div class="stat-k">优化动作</div>
            </div>
          </div>

          <!-- 甘特图 -->
          <div class="panel">
            <h2>
              📊 浇铸甘特图
              <span class="badge info">{{ mode === 'optimized' ? '优化排程' : '基准排程' }}</span>
            </h2>
            <GanttChart :result="result" />
          </div>

          <!-- 风险 + 调整 -->
          <div class="two-col">
            <div class="panel">
              <h2>🚨 断浇风险识别（{{ result.risks.length }}）</h2>
              <RiskPanel :result="result" />
            </div>
            <div class="panel">
              <h2>🛠️ 排程调整建议 / 已执行动作</h2>
              <AdjustmentPanel :result="result" />
            </div>
          </div>

          <!-- 铸机明细 -->
          <div class="panel">
            <h2>📋 铸机生产明细</h2>
            <div v-for="c in result.casters" :key="c.caster_id" class="caster-detail">
              <h4>
                {{ c.name }}
                <span class="muted">
                  周期 {{ c.cycle_minutes }}min · 缓冲 {{ c.hold_tolerance_minutes }}min
                  · 利用率 {{ c.utilization_pct }}% · 空闲 {{ c.idle_minutes }}min
                  · 钢包等待合计 {{ c.total_waited_minutes }}min
                </span>
              </h4>
              <table>
                <thead>
                  <tr>
                    <th>炉次</th><th>到达</th><th>开浇</th><th>浇完</th>
                    <th>等待(min)</th><th>上炉后空闲(min)</th><th>重量(t)</th><th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="b in c.blocks" :key="b.ladle_seq">
                    <td>#{{ b.ladle_seq }}</td>
                    <td>{{ b.arrival.slice(11, 16) }}</td>
                    <td>{{ b.start.slice(11, 16) }}</td>
                    <td>{{ b.end.slice(11, 16) }}</td>
                    <td>{{ b.waited_minutes }}</td>
                    <td>{{ b.gap_from_prev === null ? '—' : b.gap_from_prev }}</td>
                    <td>{{ b.weight_tonnes }}</td>
                    <td>
                      <span v-if="b.reflowed" class="badge purple">改派</span>
                      <span v-else-if="b.interrupted_before" class="badge high">断浇重开</span>
                      <span v-else-if="b.used_slowdown" class="badge medium">降速衔接</span>
                      <span v-else class="badge low">正常</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <div v-else class="panel placeholder">
          <p>👈 在左侧配置铸机、钢包到达计划与停机区间，</p>
          <p>点击上方「基准排程」识别断浇风险，或「优化排程」获取自动调整方案。</p>
          <p class="muted">也可以点击右上角「载入演示数据」快速体验。</p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from './api'
import ConfigEditor from './components/ConfigEditor.vue'
import GanttChart from './components/GanttChart.vue'
import RiskPanel from './components/RiskPanel.vue'
import AdjustmentPanel from './components/AdjustmentPanel.vue'

const scenarios = ref([])
const currentId = ref(null)
const config = ref(null)
const result = ref(null)
const mode = ref('baseline')
const busy = ref(false)
const apiOk = ref(false)
const toast = ref('')
const toastOk = ref(false)

function notify(msg, ok = false) {
  toast.value = msg
  toastOk.value = ok
  setTimeout(() => { toast.value = '' }, 3200)
}

function emptyConfig() {
  return reactive({ casters: [], ladles: [], downtimes: [] })
}

onMounted(async () => {
  try {
    await api.health()
    apiOk.value = true
  } catch {
    apiOk.value = false
    notify('无法连接后端 API，请确认 FastAPI 已启动')
    config.value = emptyConfig()
    return
  }
  await refreshScenarios()
})

async function refreshScenarios() {
  scenarios.value = await api.listScenarios()
  if (scenarios.value.length) {
    currentId.value = scenarios.value[0].id
    await loadScenario()
  } else {
    config.value = emptyConfig()
  }
}

async function onScenarioChange() {
  result.value = null
  await loadScenario()
}

async function loadScenario() {
  if (!currentId.value) return
  const data = await api.getScenario(currentId.value)
  config.value = reactive({
    casters: data.casters.map(c => ({
      code: c.code, name: c.name,
      cycle_minutes: c.cycle_minutes,
      hold_tolerance_minutes: c.hold_tolerance_minutes,
      capacity_heats: c.capacity_heats,
      capacity_tonnes: c.capacity_tonnes,
    })),
    ladles: data.ladles.map(l => ({
      seq: l.seq, arrival: l.arrival.slice(0, 16),
      grade: l.grade, weight_tonnes: l.weight_tonnes,
      caster_code: l.caster_code,
    })),
    downtimes: data.downtimes.map(d => ({
      caster_code: d.caster_code,
      start: d.start.slice(0, 16), end: d.end.slice(0, 16),
      reason: d.reason,
    })),
  })
}

async function createScenario() {
  const name = `手工场景 ${new Date().toLocaleString('zh-CN', { hour12: false })}`
  try {
    const s = await api.createScenario({ name, description: '前端创建' })
    await refreshScenarios()
    currentId.value = s.id
    await loadScenario()
    notify('已创建新场景', true)
  } catch (e) { notify(e.message) }
}

async function seedDemo() {
  busy.value = true
  try {
    const s = await api.seed()
    await refreshScenarios()
    currentId.value = s.id
    await loadScenario()
    await runSimulation('baseline')
    notify('演示数据已载入并完成基准模拟', true)
  } catch (e) {
    notify(e.message)
  } finally { busy.value = false }
}

async function removeScenario() {
  if (!currentId.value) return
  if (!confirm('确认删除当前场景及其历史模拟结果？')) return
  busy.value = true
  try {
    await api.deleteScenario(currentId.value)
    result.value = null
    await refreshScenarios()
    notify('场景已删除', true)
  } catch (e) {
    notify(e.message)
  } finally { busy.value = false }
}

function validateConfig() {
  if (!config.value.casters.length) return '请至少配置一台铸机'
  const codes = new Set()
  for (const c of config.value.casters) {
    if (!c.code?.trim()) return '铸机编号不能为空'
    if (!(c.cycle_minutes > 0)) return `${c.code} 浇铸周期必须大于 0`
    if (codes.has(c.code)) return `铸机编号重复：${c.code}`
    codes.add(c.code)
  }
  const seqs = new Set()
  for (const l of config.value.ladles) {
    if (!l.arrival) return `第 ${l.seq} 炉缺少到达时间`
    if (seqs.has(l.seq)) return `炉次号重复：${l.seq}`
    seqs.add(l.seq)
  }
  for (const d of config.value.downtimes) {
    if (!d.start || !d.end) return '停机区间时间不完整'
    if (d.end <= d.start) return '存在结束时间早于开始时间的停机区间'
  }
  return null
}

async function saveAndSimulate() {
  const err = validateConfig()
  if (err) { notify(err); return }
  busy.value = true
  try {
    if (!currentId.value) {
      const s = await api.createScenario({
        name: `手工场景 ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
      })
      await refreshScenarios()
      currentId.value = s.id
    }
    await api.saveConfig(currentId.value, config.value)
    notify('配置已保存', true)
    await runSimulation(mode.value)
  } catch (e) {
    notify(e.message)
  } finally { busy.value = false }
}

async function runSimulation(nextMode) {
  mode.value = nextMode
  const err = validateConfig()
  if (err) { notify(err); return }
  busy.value = true
  try {
    if (currentId.value) {
      // 先保存再模拟，保证结果与界面配置一致
      await api.saveConfig(currentId.value, config.value)
      const run = await api.simulate(currentId.value, nextMode)
      result.value = run.result
    } else {
      // 无场景时走即席模拟
      result.value = await api.adhoc({ ...config.value, mode: nextMode })
    }
  } catch (e) {
    notify(e.message)
  } finally { busy.value = false }
}

async function loadRuns() {
  if (!currentId.value) return
  const runs = await api.listRuns(currentId.value)
  if (!runs.length) { notify('暂无历史模拟结果'); return }
  const labels = runs.map((r, i) =>
    `${i + 1}. [${r.mode === 'optimized' ? '优化' : '基准'}] ${r.created_at.slice(0, 16)}`
  )
  const pick = prompt(
    `输入序号载入历史结果（共 ${runs.length} 条，最新在前）：\n` +
    labels.slice(0, 10).join('\n')
  )
  const idx = Number(pick) - 1
  if (idx >= 0 && runs[idx]) {
    result.value = runs[idx].result
    mode.value = runs[idx].mode
  }
}
</script>

<style scoped>
.app { max-width: 1760px; margin: 0 auto; padding: 0 20px 40px; }

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  gap: 20px;
  flex-wrap: wrap;
}
.brand { display: flex; gap: 14px; align-items: center; }
.logo { font-size: 38px; }
h1 { margin: 0; font-size: 20px; letter-spacing: 1px; }
.brand p { margin: 3px 0 0; font-size: 12px; color: var(--text-dim); }
.top-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.scenario-select { width: 240px; }
.api-state { font-size: 12px; margin-left: 6px; }
.api-state.ok { color: #86efac; }
.api-state.bad { color: #fca5a5; }

.main { display: grid; grid-template-columns: minmax(420px, 560px) 1fr; gap: 16px; align-items: start; }
.col { min-width: 0; }
.right { display: flex; flex-direction: column; gap: 14px; }

.run-bar { display: flex; justify-content: space-between; align-items: center; }
.mode-switch { display: flex; gap: 10px; }

.stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
.stat {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 10px;
  text-align: center;
}
.stat-v { font-size: 24px; font-weight: 700; color: var(--accent-2); }
.stat-v small { font-size: 13px; color: var(--text-dim); margin-left: 2px; }
.stat-k { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.stat.bad .stat-v { color: var(--red); }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.muted { color: var(--text-dim); font-size: 12px; font-weight: 400; }

.caster-detail { margin-bottom: 16px; }
.caster-detail:last-child { margin-bottom: 0; }
.caster-detail h4 { margin: 8px 0 6px; font-size: 13.5px; }
.caster-detail h4 .muted { margin-left: 8px; }

.placeholder { text-align: center; color: var(--text-dim); padding: 60px 20px; font-size: 14px; line-height: 2; }

@media (max-width: 1200px) {
  .main { grid-template-columns: 1fr; }
  .two-col { grid-template-columns: 1fr; }
  .stats { grid-template-columns: repeat(3, 1fr); }
}
</style>
