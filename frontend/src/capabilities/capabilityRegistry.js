export const ARTIFACT_TYPES = [
  'search_plan',
  'search_results',
  'evidence_records',
  'intel_brief',
  'archive_record',
  'watchlist_run',
  'resume_ingest',
  'candidate_matches',
  'rsi_report',
  'workflow_snapshot',
]

export const PATH_PRODUCTIZATION = {
  '/health': 'system',
  '/integrations/env': 'system',
  '/integrations/status': 'system',
  '/jobs/match': 'productized',
  '/projects/{project_id}': 'productized',
  '/projects/{project_id}/candidates': 'productized',
  '/projects/{project_id}/candidates/unique': 'productized',
  '/projects/{project_id}/jobs': 'productized',
  '/resumes/ingest': 'productized',
  '/review/feedback': 'closed',
  '/rsi/evaluate': 'productized',
  '/scenarios/meta': 'system',
  '/scenarios/run': 'productized',
  '/search/archive': 'productized',
  '/search/archive/diff': 'productized',
  '/search/archive/recent': 'productized',
  '/search/brief': 'productized',
  '/search/evidence': 'productized',
  '/search/plan': 'productized',
  '/search/run': 'productized',
  '/search/watchlist/run': 'productized',
  '/tasks/{task_id}': 'system',
  '/tasks/{task_id}/cancel': 'system',
  '/tasks/{task_id}/confirm': 'system',
  '/tasks/{task_id}/probe-feedback': 'system',
  '/tasks/{task_id}/retry': 'system',
  '/tasks/{task_id}/stream': 'system',
  '/workflow/meta': 'system',
  '/workflow/sessions': 'productized',
  '/workflow/sessions/{task_id}/nodes/{node_id}/retry': 'productized',
  '/workflow/sessions/{task_id}/nodes/{node_id}/run': 'productized',
  '/workflow/sessions/{task_id}/nodes/{node_id}/skip': 'productized',
  '/workflows/run': 'productized',
  '/workflows/validate': 'system',
}

export const WORKSPACES = [
  { id: 'chat', title: 'Chat', label: '聊天主线' },
  { id: 'workflow', title: 'WorkflowWorkspace', label: '招聘工作流' },
  { id: 'search', title: 'SearchIntelWorkspace', label: '搜索情报' },
  { id: 'archive', title: 'ArchiveWatchWorkspace', label: '归档监控' },
  { id: 'candidate', title: 'CandidateWorkspace', label: '候选人数据' },
  { id: 'evaluation', title: 'EvaluationWorkspace', label: '评估实验室' },
  { id: 'ops', title: 'OpsWorkspace', label: '运维状态' },
]

const COMMON_SEARCH_INPUTS = [
  { name: 'query', label: '搜索问题', type: 'text', required: true },
  { name: 'claim', label: '待核验 claim', type: 'text', required: false },
  { name: 'limit', label: '结果上限', type: 'number', required: false, defaultValue: 10 },
  { name: 'service', label: '搜索服务', type: 'text', required: false },
]

export const CAPABILITY_REGISTRY = [
  {
    id: 'search_plan',
    title: '生成搜索计划',
    workspace: 'search',
    description: '把用户问题拆成 query、数据源、limit 和执行约束。',
    inputs: COMMON_SEARCH_INPUTS.filter((item) => item.name !== 'claim'),
    apiCalls: [{ method: 'POST', path: '/search/plan', client: 'createSearchPlan' }],
    artifacts: ['search_plan'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'none',
    intentTags: ['search_intel', 'evidence', 'brief'],
  },
  {
    id: 'search_intel_pipeline',
    title: '执行搜索并生成证据链',
    workspace: 'search',
    description: '按 plan -> run -> evidence -> brief 生成可审查情报包；归档只作为后续可选动作。',
    inputs: COMMON_SEARCH_INPUTS,
    apiCalls: [
      { method: 'POST', path: '/search/plan', client: 'createSearchPlan' },
      { method: 'POST', path: '/search/run', client: 'runSearch' },
      { method: 'POST', path: '/search/evidence', client: 'createSearchEvidence' },
      { method: 'POST', path: '/search/brief', client: 'createSearchBrief' },
      { method: 'POST', path: '/search/archive', client: 'archiveSearchArtifact', optional: true },
    ],
    artifacts: ['search_plan', 'search_results', 'evidence_records', 'intel_brief', 'archive_record'],
    requiresConfirmation: true,
    riskLevel: 'high',
    writeScope: 'optional_archive',
    intentTags: ['search_intel', 'evidence', 'brief', 'archive'],
  },
  {
    id: 'archive_brief',
    title: '归档当前简报',
    workspace: 'archive',
    description: '将 brief 或 evidence 写入本地 intelligence archive，执行前需要二次确认。',
    inputs: [
      ...COMMON_SEARCH_INPUTS,
      { name: 'artifact_type', label: '归档类型', type: 'select', defaultValue: 'brief', options: ['brief', 'evidence'] },
    ],
    apiCalls: [{ method: 'POST', path: '/search/archive', client: 'archiveSearchArtifact' }],
    artifacts: ['archive_record'],
    requiresConfirmation: true,
    riskLevel: 'high',
    writeScope: 'archive',
    intentTags: ['archive', 'search_intel'],
  },
  {
    id: 'archive_recent',
    title: '查看最近归档',
    workspace: 'archive',
    description: '读取 recent archive，用于回看最近证据包。',
    inputs: [{ name: 'limit', label: '读取条数', type: 'number', defaultValue: 20 }],
    apiCalls: [{ method: 'GET', path: '/search/archive/recent', client: 'fetchRecentArchives' }],
    artifacts: ['archive_record'],
    requiresConfirmation: false,
    riskLevel: 'low',
    writeScope: 'none',
    intentTags: ['archive', 'recent'],
  },
  {
    id: 'archive_diff',
    title: '比较最新归档变化',
    workspace: 'archive',
    description: '比较最近两次 brief/evidence 的来源、风险和状态变化。',
    inputs: [
      { name: 'artifact_type', label: 'Artifact 类型', type: 'select', options: ['brief', 'evidence'], required: false },
      { name: 'watchlist_name', label: 'Watchlist 名称', type: 'text', required: false },
    ],
    apiCalls: [{ method: 'GET', path: '/search/archive/diff', client: 'fetchArchiveDiff' }],
    artifacts: ['archive_record'],
    requiresConfirmation: false,
    riskLevel: 'low',
    writeScope: 'none',
    intentTags: ['archive', 'diff', 'watchlist'],
  },
  {
    id: 'watchlist_run',
    title: '运行 Watchlist 监控',
    workspace: 'archive',
    description: '批量运行监控条目，默认会写入归档，执行前必须确认。',
    inputs: [
      { name: 'itemsText', label: '监控条目', type: 'textarea', required: true },
      { name: 'limit', label: '每项上限', type: 'number', defaultValue: 10 },
      { name: 'archive', label: '写入归档', type: 'boolean', defaultValue: true },
      { name: 'service', label: '搜索服务', type: 'text', required: false },
    ],
    apiCalls: [{ method: 'POST', path: '/search/watchlist/run', client: 'runSearchWatchlist' }],
    artifacts: ['watchlist_run', 'archive_record'],
    requiresConfirmation: true,
    riskLevel: 'high',
    writeScope: 'archive',
    intentTags: ['watchlist', 'archive', 'monitor'],
  },
  {
    id: 'resume_ingest',
    title: '简历 ingest',
    workspace: 'candidate',
    description: '把本地简历文件转成候选人向量和 markdown preview，可选写库。',
    inputs: [
      { name: 'file_path', label: '本地文件路径', type: 'text', required: true },
      { name: 'candidate_id', label: 'candidate_id', type: 'text', required: true },
      { name: 'write_database', label: '写入数据库', type: 'boolean', defaultValue: false },
    ],
    apiCalls: [{ method: 'POST', path: '/resumes/ingest', client: 'ingestResume' }],
    artifacts: ['resume_ingest'],
    requiresConfirmation: true,
    riskLevel: 'high',
    writeScope: 'candidate_store',
    intentTags: ['candidate', 'resume', 'ingest'],
  },
  {
    id: 'candidate_match',
    title: '职位匹配候选人',
    workspace: 'candidate',
    description: '根据岗位 query 检索候选人向量库并展示 score、metadata 和解释入口。',
    inputs: [
      { name: 'query', label: '岗位/能力 query', type: 'textarea', required: true },
      { name: 'top_k', label: '返回数量', type: 'number', defaultValue: 5 },
    ],
    apiCalls: [{ method: 'POST', path: '/jobs/match', client: 'matchJobs' }],
    artifacts: ['candidate_matches'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'none',
    intentTags: ['candidate', 'match', 'job'],
  },
  {
    id: 'rsi_evaluate',
    title: '运行 RSI 评估',
    workspace: 'evaluation',
    description: '执行 local/full RSI 评估，展示 pass/fail、阈值和 live 风险。',
    inputs: [
      { name: 'suite', label: 'Suite', type: 'text', defaultValue: 'candidate_evaluation_core' },
      { name: 'threshold', label: '阈值', type: 'number', required: false },
      { name: 'mode', label: '模式', type: 'select', defaultValue: 'local', options: ['local', 'full'] },
      { name: 'allow_live', label: '允许 live 调用', type: 'boolean', defaultValue: false },
      { name: 'search_service', label: '搜索服务', type: 'text', required: false },
      { name: 'llm_service', label: 'LLM 服务', type: 'text', defaultValue: 'openrouter_evidence_judge' },
    ],
    apiCalls: [{ method: 'POST', path: '/rsi/evaluate', client: 'evaluateRsi' }],
    artifacts: ['rsi_report'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'none',
    intentTags: ['evaluation', 'rsi', 'quality'],
  },
  {
    id: 'workflow_a',
    title: '进入岗位画像',
    workspace: 'workflow',
    description: '启动四场景 A，生成岗位画像、JD、能力矩阵和面试题。',
    inputs: [{ name: 'input', label: '招聘目标', type: 'textarea', required: true }],
    apiCalls: [{ method: 'POST', path: '/scenarios/run', client: 'runScenario', scenario: 'A' }],
    artifacts: ['workflow_snapshot'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'task_store',
    intentTags: ['workflow', 'job_profile'],
  },
  {
    id: 'workflow_b',
    title: '进入人才地图',
    workspace: 'workflow',
    description: '启动四场景 B，生成目标公司、搜索关键词和触达策略。',
    inputs: [{ name: 'input', label: '招聘目标', type: 'textarea', required: true }],
    apiCalls: [{ method: 'POST', path: '/scenarios/run', client: 'runScenario', scenario: 'B' }],
    artifacts: ['workflow_snapshot'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'task_store',
    intentTags: ['workflow', 'talent_map', 'search_intel'],
  },
  {
    id: 'workflow_atomic',
    title: '打开原子节点控制',
    workspace: 'workflow',
    description: '进入 WorkflowWorkspace，按单个节点 run/retry/skip 控制 A/B/C/D。',
    inputs: [{ name: 'input', label: '招聘目标', type: 'textarea', required: true }],
    apiCalls: [
      { method: 'GET', path: '/workflow/meta', client: 'fetchWorkflowMeta' },
      { method: 'POST', path: '/workflow/sessions', client: 'createWorkflowSession' },
      { method: 'POST', path: '/workflow/sessions/{task_id}/nodes/{node_id}/run', client: 'runWorkflowNode' },
      { method: 'POST', path: '/workflow/sessions/{task_id}/nodes/{node_id}/retry', client: 'retryWorkflowNode' },
      { method: 'POST', path: '/workflow/sessions/{task_id}/nodes/{node_id}/skip', client: 'skipWorkflowNode' },
    ],
    artifacts: ['workflow_snapshot'],
    requiresConfirmation: true,
    riskLevel: 'medium',
    writeScope: 'task_store',
    intentTags: ['workflow', 'atomic'],
  },
  {
    id: 'ops_health',
    title: '检查系统健康',
    workspace: 'ops',
    description: '读取 health、integrations/status 和 OpenAPI，用于确认服务可用性。',
    inputs: [],
    apiCalls: [
      { method: 'GET', path: '/health', client: 'fetchHealth' },
      { method: 'GET', path: '/integrations/status', client: 'fetchIntegrationStatus' },
      { method: 'GET', path: '/scenarios/meta', client: 'fetchMeta' },
    ],
    artifacts: [],
    requiresConfirmation: false,
    riskLevel: 'low',
    writeScope: 'none',
    intentTags: ['ops', 'health', 'integration'],
  },
  {
    id: 'ops_env_save',
    title: '保存 API Key',
    workspace: 'ops',
    description: '保存 allowlist 环境变量到本地 .env，只能本地请求，执行前必须确认。',
    inputs: [{ name: 'values', label: '环境变量 values', type: 'object', required: true }],
    apiCalls: [{ method: 'POST', path: '/integrations/env', client: 'saveIntegrationEnv' }],
    artifacts: [],
    requiresConfirmation: true,
    riskLevel: 'high',
    writeScope: 'local_config',
    intentTags: ['ops', 'env', 'api_key'],
  },
  {
    id: 'review_feedback',
    title: '查看 Review Feedback',
    workspace: 'ops',
    description: '读取 review feedback 占位状态；当前后端返回 pending_implementation。',
    inputs: [],
    apiCalls: [{ method: 'GET', path: '/review/feedback', client: 'fetchReviewFeedback' }],
    artifacts: [],
    requiresConfirmation: false,
    riskLevel: 'low',
    writeScope: 'none',
    intentTags: ['ops', 'review'],
  },
]

const INTENT_KEYWORDS = {
  search_intel: ['搜索', '证据', '情报', '来源', '核验', '简报', 'source', 'evidence', 'brief', 'intel', 'search'],
  archive: ['归档', 'archive', 'recent', 'diff', '变化', '监控'],
  watchlist: ['watchlist', '监控', '定期', '变化'],
  candidate: ['候选人', '简历', 'resume', 'candidate', 'match', '匹配'],
  evaluation: ['评估', 'rsi', 'evaluate', '阈值', '测试'],
  ops: ['health', 'api key', 'key', '集成', '状态', 'integrations', 'env'],
  workflow: ['岗位', '人才地图', '周报', '招聘', '面试', 'workflow', 'jd'],
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

export function detectIntent(input) {
  const text = normalizeText(input)
  if (!text) return 'workflow'
  for (const [intent, keywords] of Object.entries(INTENT_KEYWORDS)) {
    if (keywords.some((keyword) => text.includes(keyword.toLowerCase()))) return intent
  }
  return 'workflow'
}

export function getCapabilityById(id) {
  return CAPABILITY_REGISTRY.find((capability) => capability.id === id) || null
}

export function getCapabilitiesByWorkspace(workspace) {
  return CAPABILITY_REGISTRY.filter((capability) => capability.workspace === workspace)
}

export function suggestCapabilitiesForInput(input, limit = 3) {
  const intent = detectIntent(input)
  const preferred = CAPABILITY_REGISTRY.filter((capability) => capability.intentTags.includes(intent))
  const fallback = CAPABILITY_REGISTRY.filter((capability) => !preferred.includes(capability))
  return [...preferred, ...fallback].slice(0, limit)
}

export function productizationSummary() {
  return Object.entries(PATH_PRODUCTIZATION).reduce(
    (summary, [, status]) => ({
      ...summary,
      [status]: (summary[status] || 0) + 1,
    }),
    {},
  )
}
