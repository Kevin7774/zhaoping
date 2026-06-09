// Thin API client. All orchestration logic lives in the backend; the frontend
// only fetches the protocol (meta) and listens to task state.

const BASE = import.meta.env.VITE_API_BASE ?? '/api'
export const API_DOCS_URL = BASE ? `${BASE}/docs` : '/docs'

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

function queryString(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, value)
  }
  const serialized = search.toString()
  return serialized ? `?${serialized}` : ''
}

function request(path, options = {}) {
  const { body, query, ...fetchOptions } = options
  const init = { ...fetchOptions }
  if (body !== undefined) {
    init.method = init.method || 'POST'
    init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) }
    init.body = JSON.stringify(body)
  }
  return fetch(`${BASE}${path}${queryString(query)}`, init).then(handle)
}

export function fetchHealth() {
  return request('/health')
}

export function fetchMeta() {
  return request('/scenarios/meta')
}

export function fetchWorkflowMeta() {
  return request('/workflow/meta')
}

export function fetchOpenApi() {
  return request('/openapi.json')
}

export function fetchIntegrationStatus() {
  return request('/integrations/status')
}

export function saveIntegrationEnv(values) {
  return request('/integrations/env', {
    method: 'POST',
    body: { values },
  })
}

export function createSearchPlan(payload) {
  return request('/search/plan', {
    method: 'POST',
    body: payload,
  })
}

export function runSearch(payload) {
  return request('/search/run', {
    method: 'POST',
    body: payload,
  })
}

export function createSearchEvidence(payload) {
  return request('/search/evidence', {
    method: 'POST',
    body: payload,
  })
}

export function createSearchBrief(payload) {
  return request('/search/brief', {
    method: 'POST',
    body: payload,
  })
}

export function archiveSearchArtifact(payload) {
  return request('/search/archive', {
    method: 'POST',
    body: payload,
  })
}

export function fetchRecentArchives(params = {}) {
  return request('/search/archive/recent', {
    query: params,
  })
}

export function fetchArchiveDiff(params = {}) {
  return request('/search/archive/diff', {
    query: params,
  })
}

export function runSearchWatchlist(payload) {
  return request('/search/watchlist/run', {
    method: 'POST',
    body: payload,
  })
}

export function ingestResume(payload) {
  return request('/resumes/ingest', {
    method: 'POST',
    body: payload,
  })
}

export function importLocalResume(payload) {
  return request('/resumes/local-import', {
    method: 'POST',
    body: payload,
  })
}

export function matchJobs(payload) {
  return request('/jobs/match', {
    method: 'POST',
    body: payload,
  })
}

export function evaluateRsi(payload) {
  return request('/rsi/evaluate', {
    method: 'POST',
    body: payload,
  })
}

export function fetchReviewFeedback() {
  return request('/review/feedback')
}

export function runScenario(scenario, input, options = {}) {
  return request('/scenarios/run', {
    method: 'POST',
    body: {
      scenario,
      input,
      team_constraint: options.teamConstraint || '真机泛化',
      aperture_weight: options.apertureWeight ?? 0.7,
      frontend_state: {
        scenario,
        aperture_anchor: {
          team_constraint: options.teamConstraint || '真机泛化',
          aperture_weight: options.apertureWeight ?? 0.7,
        },
      },
    },
  })
}

export function createWorkflowSession(scenario, input, options = {}) {
  return request('/workflow/sessions', {
    method: 'POST',
    body: {
      scenario,
      input,
      team_constraint: options.teamConstraint || '真机泛化',
      aperture_weight: options.apertureWeight ?? 0.7,
      frontend_state: {
        ...(options.frontendState || {}),
        mode: 'atomic',
        scenario,
      },
    },
  })
}

export function runWorkflowNode(taskId, nodeId, payload = {}) {
  return request(`/workflow/sessions/${taskId}/nodes/${nodeId}/run`, {
    method: 'POST',
    body: payload,
  })
}

export function retryWorkflowNode(taskId, nodeId, payload = {}) {
  return request(`/workflow/sessions/${taskId}/nodes/${nodeId}/retry`, {
    method: 'POST',
    body: payload,
  })
}

export function skipWorkflowNode(taskId, nodeId, reason = '用户跳过原子节点') {
  return request(`/workflow/sessions/${taskId}/nodes/${nodeId}/skip`, {
    method: 'POST',
    body: { reason },
  })
}

export function fetchTask(taskId) {
  return request(`/tasks/${taskId}`)
}

export function taskStreamUrl(taskId) {
  return `${BASE}/tasks/${taskId}/stream`
}

export function cancelTask(taskId) {
  return request(`/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
}

export function retryTask(taskId) {
  return request(`/tasks/${taskId}/retry`, {
    method: 'POST',
  })
}

export function confirmTask(taskId, decision, edits) {
  return request(`/tasks/${taskId}/confirm`, {
    method: 'POST',
    body: { decision, edits: edits || null },
  })
}

export function sendProbeFeedback(taskId, probeId, answered, note) {
  return request(`/tasks/${taskId}/probe-feedback`, {
    method: 'POST',
    body: { probe_id: probeId, answered, note: note || null },
  })
}
