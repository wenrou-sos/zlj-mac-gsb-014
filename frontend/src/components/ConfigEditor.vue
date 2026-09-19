<template>
  <div class="editor">
    <div class="toolbar">
      <button class="primary" :disabled="busy" @click="$emit('save')">
        {{ busy ? '保存中…' : '💾 保存配置' }}
      </button>
      <button :disabled="busy" @click="$emit('reset')">↺ 重置为已保存</button>
      <span class="hint">修改后点击「保存配置」，再运行模拟</span>
    </div>

    <!-- 铸机 -->
    <section class="block">
      <h3>🏭 铸机配置</h3>
      <table>
        <thead>
          <tr>
            <th style="width:80px">编号</th><th style="width:140px">名称</th>
            <th>浇铸周期(min)</th><th>降速缓冲(min)</th>
            <th>炉数能力</th><th>吨位能力(t)</th><th style="width:46px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in config.casters" :key="i">
            <td><input v-model="c.code" /></td>
            <td><input v-model="c.name" /></td>
            <td><input type="number" min="1" v-model.number="c.cycle_minutes" /></td>
            <td><input type="number" min="0" v-model.number="c.hold_tolerance_minutes" /></td>
            <td><input type="number" min="0" v-model.number="c.capacity_heats"
                       placeholder="不限" /></td>
            <td><input type="number" min="0" v-model.number="c.capacity_tonnes"
                       placeholder="不限" /></td>
            <td><button class="sm danger" @click="config.casters.splice(i, 1)">删</button></td>
          </tr>
        </tbody>
      </table>
      <button class="sm add" @click="addCaster">＋ 新增铸机</button>
    </section>

    <!-- 钢包 -->
    <section class="block">
      <h3>🪣 钢包（炉次）到达计划
        <span class="sub">指定铸机留空 = 由系统自动分配</span>
      </h3>
      <div class="ladle-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:64px">炉次号</th><th style="width:190px">到达时间</th>
              <th style="width:110px">钢种</th><th style="width:110px">单重(t)</th>
              <th style="width:150px">指定铸机</th><th style="width:46px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(l, i) in config.ladles" :key="i">
              <td><input type="number" min="1" v-model.number="l.seq" /></td>
              <td><input type="datetime-local" v-model="l.arrival" /></td>
              <td><input v-model="l.grade" /></td>
              <td><input type="number" min="1" v-model.number="l.weight_tonnes" /></td>
              <td>
                <select v-model="l.caster_code">
                  <option :value="null">自动分配</option>
                  <option v-for="c in config.casters" :key="c.code" :value="c.code">
                    {{ c.code }} {{ c.name }}
                  </option>
                </select>
              </td>
              <td><button class="sm danger" @click="config.ladles.splice(i, 1)">删</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="row-actions">
        <button class="sm add" @click="addLadle">＋ 新增钢包</button>
        <button class="sm" @click="addLadle(45)">＋ 45 分钟后追加一炉</button>
      </div>
    </section>

    <!-- 停机 -->
    <section class="block">
      <h3>🔧 设备停机区间</h3>
      <table>
        <thead>
          <tr>
            <th style="width:150px">铸机</th>
            <th style="width:190px">开始</th><th style="width:190px">结束</th>
            <th>原因</th><th style="width:46px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(d, i) in config.downtimes" :key="i">
            <td>
              <select v-model="d.caster_code">
                <option value="" disabled>请选择</option>
                <option v-for="c in config.casters" :key="c.code" :value="c.code">
                  {{ c.code }} {{ c.name }}
                </option>
              </select>
            </td>
            <td><input type="datetime-local" v-model="d.start" /></td>
            <td><input type="datetime-local" v-model="d.end" /></td>
            <td><input v-model="d.reason" /></td>
            <td><button class="sm danger" @click="config.downtimes.splice(i, 1)">删</button></td>
          </tr>
        </tbody>
      </table>
      <button class="sm add" @click="addDowntime">＋ 新增停机区间</button>
    </section>
  </div>
</template>

<script setup>
import { watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
defineEmits(['save', 'reset', 'update:modelValue'])

const config = props.modelValue

watch(() => props.modelValue, () => {}, { deep: true })

function pad(n) { return String(n).padStart(2, '0') }
function localInput(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function addCaster() {
  const n = config.casters.length + 1
  config.casters.push({
    code: `CC${n}`, name: `${n}#连铸机`,
    cycle_minutes: 45, hold_tolerance_minutes: 15,
    capacity_heats: null, capacity_tonnes: null,
  })
}

function addLadle(plusMinutes = 0) {
  const nextSeq = config.ladles.reduce((m, l) => Math.max(m, Number(l.seq) || 0), 0) + 1
  let base
  if (plusMinutes && config.ladles.length) {
    const last = config.ladles.map(l => l.arrival).sort().at(-1)
    base = new Date(new Date(last).getTime() + plusMinutes * 60000)
  } else {
    base = new Date()
    base.setMinutes(0, 0, 0)
    base.setHours(base.getHours() + 1)
  }
  config.ladles.push({
    seq: nextSeq, arrival: localInput(base), grade: 'Q235B',
    weight_tonnes: 120, caster_code: config.casters[0]?.code || null,
  })
}

function addDowntime() {
  const start = new Date(); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 2)
  const end = new Date(start.getTime() + 3600_000)
  config.downtimes.push({
    caster_code: config.casters[0]?.code || '',
    start: localInput(start), end: localInput(end), reason: '设备维护',
  })
}
</script>

<style scoped>
.editor { display: flex; flex-direction: column; gap: 18px; }
.toolbar { display: flex; align-items: center; gap: 10px; }
.hint { font-size: 12px; color: var(--text-dim); }

.block h3 {
  margin: 0 0 8px;
  font-size: 13.5px;
  font-weight: 600;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.block h3 .sub { font-size: 11.5px; color: var(--text-dim); font-weight: 400; }

.ladle-wrap { max-height: 320px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.ladle-wrap table { border-collapse: separate; }
.ladle-wrap thead th { position: sticky; top: 0; background: var(--panel-2); z-index: 1; }

.add { margin-top: 8px; border-style: dashed; color: var(--accent-2); }
.row-actions { display: flex; gap: 8px; margin-top: 8px; }
</style>
