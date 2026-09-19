<template>
  <div class="adjusts">
    <div v-if="!result.adjustments.length" class="empty">
      <span v-if="result.mode === 'baseline'">当前为基准排程，运行「优化排程」可自动应用调整。</span>
      <span v-else>无需调整，排程已是优化状态。</span>
    </div>
    <div v-for="(a, i) in result.adjustments" :key="i" class="adj-card">
      <span class="badge" :class="badgeClass(a.type)">{{ a.type_label }}</span>
      <span v-if="a.ladle_seq" class="seq">第 {{ a.ladle_seq }} 炉</span>
      <span class="desc">{{ a.description }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ result: { type: Object, required: true } })
function badgeClass(type) {
  return { reassign: 'purple', hold: 'info', shift: 'medium', capacity: 'high' }[type] || 'info'
}
</script>

<style scoped>
.adjusts { display: flex; flex-direction: column; gap: 8px; max-height: 460px; overflow-y: auto; }
.empty { font-size: 12.5px; color: var(--text-dim); padding: 14px; text-align: center;
  border: 1px dashed var(--border); border-radius: 8px; }
.adj-card {
  display: flex; align-items: center; gap: 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12.5px;
  line-height: 1.5;
}
.adj-card .seq { color: var(--text-dim); font-size: 11.5px; white-space: nowrap; }
.desc { color: var(--text); }
</style>
