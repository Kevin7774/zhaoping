// Thin API client. All orchestration logic lives in the backend; the frontend
// only fetches the protocol (meta) and listens to task state.

const BASE = '/api'

async function handle(res) {
  if (!res.ok) {
    let detail
    try {
      detail = (await res.json()).detail
    } catch {
      detail = res.statusText
    }
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export function fetchMeta() {
  return fetch(`${BASE}/scenarios/meta`).then(handle)
}

export function runScenario(scenario, input) {
  return fetch(`${BASE}/scenarios/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario, input }),
  }).then(handle)
}

export function fetchTask(taskId) {
  return fetch(`${BASE}/tasks/${taskId}`).then(handle)
}

export function confirmTask(taskId, decision, edits) {
  return fetch(`${BASE}/tasks/${taskId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, edits: edits || null }),
  }).then(handle)
}
