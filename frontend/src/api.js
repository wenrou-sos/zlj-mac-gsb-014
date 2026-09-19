const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = typeof data.detail === 'string'
      ? data.detail
      : (data.detail?.[0]?.msg || `请求失败（${res.status}）`)
    throw new Error(msg)
  }
  return data
}

export const api = {
  health: () => request('/api/health'),
  listScenarios: () => request('/api/scenarios'),
  createScenario: (payload) => request('/api/scenarios', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  getScenario: (id) => request(`/api/scenarios/${id}`),
  saveConfig: (id, config) => request(`/api/scenarios/${id}/config`, {
    method: 'PUT', body: JSON.stringify(config),
  }),
  deleteScenario: (id) => request(`/api/scenarios/${id}`, { method: 'DELETE' }),
  simulate: (id, mode, persist = true) =>
    request(`/api/scenarios/${id}/simulate?mode=${mode}&persist=${persist}`, {
      method: 'POST',
    }),
  listRuns: (id) => request(`/api/scenarios/${id}/runs`),
  adhoc: (payload) => request('/api/simulate', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  seed: () => request('/api/seed', { method: 'POST' }),
}

// datetime-local 输入框值（YYYY-MM-DDTHH:mm）与后端 datetime 互通
export function toLocalInput(iso) {
  if (!iso) return ''
  return iso.slice(0, 16)
}
