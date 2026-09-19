<template>
  <div class="risks">
    <div v-if="!result.risks.length" class="empty">
      ✅ 未识别到断浇风险，排程节奏正常。
    </div>

    <div v-for="(r, i) in result.risks" :key="i" class="risk-card" :class="r.severity">
      <div class="risk-head">
        <span class="badge" :class="r.severity">{{ severityText[r.severity] }}</span>
        <span class="risk-type">{{ r.type_label }}</span>
        <span v-if="r.ladle_seq" class="risk-seq">第 {{ r.ladle_seq }} 炉</span>
        <span v-if="r.time" class="risk-time">{{ r.time.slice(5) }}</span>
      </div>
      <p class="risk-msg">{{ r.message }}</p>
      <p class="risk-sug">💡 {{ r.suggestion }}</p>
      <div class="risk-tag">建议动作：{{ r.adjust_label }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ result: { type: Object, required: true } })
const severityText = { high: '高风险', medium: '中风险', low: '低风险' }
</script>

<style scoped>
.risks { display: flex; flex-direction: column; gap: 10px; max-height: 460px; overflow-y: auto; }
.empty {
  color: #86efac;
  font-size: 13px;
  padding: 18px;
  border: 1px solid rgba(34,197,94,.3);
  background: rgba(34,197,94,.07);
  border-radius: 8px;
  text-align: center;
}
.risk-card {
  border-radius: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  border-left-width: 4px;
}
.risk-card.high { border-left-color: var(--red); }
.risk-card.medium { border-left-color: var(--amber); }
.risk-card.low { border-left-color: var(--green); }
.risk-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.risk-type { font-size: 13px; font-weight: 600; }
.risk-seq, .risk-time { font-size: 11.5px; color: var(--text-dim); }
.risk-msg { margin: 4px 0 6px; font-size: 12.5px; line-height: 1.6; color: var(--text); }
.risk-sug { margin: 0 0 6px; font-size: 12.5px; line-height: 1.6; color: #fcd34d; }
.risk-tag { font-size: 11.5px; color: var(--text-dim); }
</style>
