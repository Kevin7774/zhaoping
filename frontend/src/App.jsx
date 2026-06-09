import { useCallback, useMemo, useReducer, useRef, useState } from 'react'
import {
  API_DOCS_URL,
  archiveSearchArtifact,
  createSearchBrief,
  createSearchEvidence,
  createSearchPlan,
  evaluateRsi,
  fetchArchiveDiff,
  fetchHealth,
  fetchIntegrationStatus,
  fetchOpenApi,
  fetchRecentArchives,
  fetchReviewFeedback,
  ingestResume,
  matchJobs,
  runSearch,
  runSearchWatchlist,
  saveIntegrationEnv,
} from './api.js'
import {
  CAPABILITY_REGISTRY,
  PATH_PRODUCTIZATION,
  getCapabilityById,
  suggestCapabilitiesForInput,
} from './capabilities/capabilityRegistry.js'
import { useAgentWorkspace } from './hooks/useAgentWorkspace.js'
import AgentFlow from './components/AgentFlow.jsx'
import AtomicWorkflowPanel from './components/AtomicWorkflowPanel.jsx'
import CapabilityDrawer from './components/workbench/CapabilityDrawer.jsx'
import ChatShell from './components/workbench/ChatShell.jsx'
import HumanGate from './components/HumanGate.jsx'
import JsonView from './components/JsonView.jsx'
import LogStream from './components/LogStream.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import SharedContextPanel from './components/context/SharedContextPanel.jsx'
import ModuleGraph from './components/modules/ModuleGraph.jsx'
import WorkspaceTabs from './components/workbench/WorkspaceTabs.jsx'
import {
  INITIAL_WORKBENCH_STATE,
  createArtifact,
  createRun,
  workbenchReducer,
} from './workbench/workbenchState.js'

const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head']
const TERMINAL_STATUS = new Set(['done', 'error', 'cancelled'])

const STATUS_FALLBACK = {
  idle: { name_zh: '未运行', help: '等待任务启动。' },
  processing: { name_zh: '执行中', help: 'AgentRunner 正在处理当前节点。' },
  awaiting_human: { name_zh: '等待人工确认', help: '流程暂停在人工门控。' },
  done: { name_zh: '已完成', help: '报告已生成。' },
  error: { name_zh: '已终止', help: '任务异常结束。' },
  cancelled: { name_zh: '已取消', help: '任务已取消。' },
}

const INTEGRATION_STATUS_LABELS = {
  active: '已接入',
  available: '已接入',
  missing_key: '缺少 Key',
  missing_tool: '缺少工具',
  manual_setup: '需人工配置',
  disabled: '未接入',
  not_configured: '未接入',
}

const SCENARIO_DISPLAY = {
  A: { title: '岗位画像', description: '生成岗位画像、JD、能力矩阵、面试题' },
  B: { title: '人才地图', description: '构建目标公司、搜索关键词、触达策略' },
  C: { title: '候选评估', description: '输出评分卡、证据链、追问清单' },
  D: { title: '招聘周报', description: '汇总进展、风险、下周动作' },
}

function parseApiCatalog(openapi) {
  const paths = openapi?.paths || {}
  return Object.entries(paths).flatMap(([path, methods]) =>
    HTTP_METHODS.filter((method) => methods?.[method]).map((method) => {
      const spec = methods[method]
      return {
        method: method.toUpperCase(),
        path,
        summary: spec.summary || spec.operationId || '未命名接口',
        description: spec.description || '',
        operationId: spec.operationId,
        hasBody: Boolean(spec.requestBody),
        parameters: spec.parameters || [],
        responses: Object.keys(spec.responses || {}),
      }
    }),
  )
}

function integrationStatusLabel(status) {
  return INTEGRATION_STATUS_LABELS[status] || status || '未知'
}

function integrationStatusTone(status) {
  if (status === 'active' || status === 'available') return 'ready'
  if (status === 'missing_key' || status === 'missing_tool' || status === 'manual_setup') return 'warning'
  if (status === 'disabled' || status === 'not_configured') return 'muted'
  return 'error'
}

function integrationCredentialRows(integrationStatus) {
  const rows = new Map()
  for (const service of integrationStatus?.services || []) {
    for (const credential of service.credentials || []) {
      if (!credential?.env) continue
      const existing = rows.get(credential.env)
      rows.set(credential.env, {
        env: credential.env,
        present: Boolean((existing && existing.present) || credential.present),
        services: [...(existing?.services || []), service.name_zh || service.name],
      })
    }
  }
  return [...rows.values()].sort((a, b) => a.env.localeCompare(b.env))
}

function compactValue(value) {
  if (value === null || value === undefined || value === '') return null
  if (Array.isArray(value)) {
    const items = value
      .map((item) => {
        if (typeof item === 'string' || typeof item === 'number') return String(item)
        if (item && typeof item === 'object') return item.name || item.title || item.source_key || item.label
        return null
      })
      .filter(Boolean)
    if (!items.length) return `${value.length} 项`
    return items.slice(0, 3).join(' / ') + (items.length > 3 ? ` 等 ${items.length} 项` : '')
  }
  if (typeof value === 'object') {
    if (value.status) return String(value.status)
    if (value.name || value.title || value.label) return String(value.name || value.title || value.label)
    return `${Object.keys(value).length} 个字段`
  }
  return String(value)
}

function outputFacts(output) {
  if (!output || typeof output !== 'object') return []
  const preferredKeys = [
    '岗位',
    'role_key',
    '技术层',
    '目标公司',
    '动态目标公司',
    '高校实验室',
    '动态实验室',
    '能力矩阵',
    '面试问题',
    '推荐信源',
    '证据记录',
    '校准状态',
    '实时检索',
  ]
  const facts = []
  for (const key of preferredKeys) {
    if (!(key in output)) continue
    const value = compactValue(output[key])
    if (value) facts.push({ label: key, value })
  }
  if (facts.length >= 4) return facts.slice(0, 4)
  for (const [key, rawValue] of Object.entries(output)) {
    if (facts.some((fact) => fact.label === key)) continue
    const value = compactValue(rawValue)
    if (value) facts.push({ label: key, value })
    if (facts.length >= 4) break
  }
  return facts
}

function LiveTaskSummary({ task, agentNodes }) {
  if (!task) return null
  const completed = Array.isArray(task.steps_done) ? task.steps_done : []
  const latest = completed.at(-1)
  const latestFacts = outputFacts(latest?.output)
  const activeNode = agentNodes.find((node) => node.status === 'active' || node.status === 'awaiting')
  const totalSteps = task.total_steps || agentNodes.length || 0
  const hint =
    task.status === 'awaiting_human'
      ? '等待人工确认'
      : task.status === 'done'
        ? '交付报告已生成'
        : task.status === 'cancelled'
          ? '任务已取消'
          : '执行中'

  return (
    <section className={`live-task-summary status-${task.status}`} aria-label="实时产出">
      <div className="live-summary-head">
        <div>
          <div className="section-label">实时产出</div>
          <h2>{latest?.label || activeNode?.label || '等待第一条结构化结果'}</h2>
        </div>
        <span>已完成步骤 {completed.length}/{totalSteps}</span>
      </div>
      <p className="live-summary-hint">{hint}</p>
      {latest ? (
        <div className="live-output-card">
          <div className="live-output-title">最新信息 · {latest.agent_id}</div>
          {latestFacts.length ? (
            <div className="live-fact-grid">
              {latestFacts.map((fact) => (
                <div className="live-fact" key={`${latest.agent_id}-${fact.label}`}>
                  <span>{fact.label}</span>
                  <strong>{fact.value}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="live-empty">本步骤已产出结构化结果，可在下方节点详情里展开。</div>
          )}
        </div>
      ) : (
        <div className="live-empty">正在拆解需求，第一条实际信息会在这里出现。</div>
      )}
      {completed.length > 0 && (
        <div className="live-step-list" aria-label="已完成步骤">
          {completed.map((step, index) => (
            <span key={`${step.agent_id}-${step.label}-${index}`}>
              {String(index + 1).padStart(2, '0')} {step.label}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function buildSearchPayload(prompt) {
  return {
    query: prompt.trim(),
    claim: prompt.trim(),
    limit: 10,
  }
}

function parseWatchlistItems(text) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, query, claim, tags] = line.split('|').map((part) => part?.trim())
      return {
        name: name || query || line,
        query: query || name || line,
        claim: claim || null,
        tags: tags ? tags.split(',').map((tag) => tag.trim()).filter(Boolean) : [],
      }
    })
}

function latestArtifact(artifacts, type) {
  return artifacts.find((artifact) => artifact.type === type) || null
}

export default function App() {
  const [input, setInput] = useState('')
  const [chatPrompt, setChatPrompt] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(true)
  const [apiPanelOpen, setApiPanelOpen] = useState(false)
  const [completedPanelOpen, setCompletedPanelOpen] = useState(false)
  const [reportPageOpen, setReportPageOpen] = useState(false)
  const [apiCatalog, setApiCatalog] = useState(null)
  const [apiCatalogError, setApiCatalogError] = useState(null)
  const [apiCatalogBusy, setApiCatalogBusy] = useState(false)
  const [integrationStatus, setIntegrationStatus] = useState(null)
  const [integrationStatusError, setIntegrationStatusError] = useState(null)
  const [integrationStatusBusy, setIntegrationStatusBusy] = useState(false)
  const [credentialDrafts, setCredentialDrafts] = useState({})
  const [credentialSaveBusy, setCredentialSaveBusy] = useState(null)
  const [credentialSaveError, setCredentialSaveError] = useState(null)
  const [credentialSaveMessage, setCredentialSaveMessage] = useState(null)
  const [workbenchState, dispatchWorkbench] = useReducer(workbenchReducer, INITIAL_WORKBENCH_STATE)
  const apiCatalogBusyRef = useRef(false)
  const integrationStatusBusyRef = useRef(false)

  const workspace = useAgentWorkspace()
  const {
    activeTaskId,
    activeModuleId,
    agentNodes,
    agentContext,
    apertureWeight,
    auditEvents,
    busy,
    cancelTask,
    currentScenario,
    currentScenarioId,
    debouncedApertureWeight,
    debouncedTeamConstraint,
    dismissModuleCall,
    editTask,
    editModuleCall,
    error,
    isStreaming,
    moduleHistory,
    moduleStatuses,
    pendingModuleAwaiting,
    pendingModuleCall,
    rejectTask,
    rejectModuleCall,
    recommendedModuleCalls,
    requestModuleCall,
    scenarios,
    setApertureWeight,
    setCurrentScenarioId,
    setTeamConstraint,
    startModule,
    approveTask,
    approveModuleCall,
    task,
    taskStatus,
    taskStatuses,
    teamConstraint,
  } = workspace

  const running = task && !TERMINAL_STATUS.has(task.status)
  const currentDisplay = SCENARIO_DISPLAY[currentScenarioId] || {
    title: currentScenario?.name_zh?.replace(/^场景\s*[A-Z]：/, '') || '未选择',
    description: currentScenario?.input_hint || '',
  }
  const statusMeta = taskStatuses[taskStatus] || STATUS_FALLBACK[taskStatus] || { name_zh: taskStatus, help: '' }
  const activeNode = agentNodes.find((node) => node.status === 'active' || node.status === 'awaiting')
  const totalSteps = agentNodes.length || currentScenario?.steps?.length || 0
  const doneSteps = agentNodes.filter((node) => node.status === 'done').length
  const progress = totalSteps ? Math.min(100, Math.round((doneSteps / totalSteps) * 100)) : 0
  const metaOnline = Boolean(scenarios.length) && !error
  const reportReady = Boolean(task?.status === 'done' && task.result)
  const reportTitle = task?.result?.human_report?.title || task?.result?.title || '交付报告'
  const capabilityCatalog = useMemo(() => CAPABILITY_REGISTRY, [])
  const selectedWorkspace = workbenchState.selectedWorkspace

  const refreshApiCatalog = useCallback(async () => {
    if (apiCatalogBusyRef.current) return
    apiCatalogBusyRef.current = true
    setApiCatalogBusy(true)
    setApiCatalogError(null)
    try {
      const openapi = await fetchOpenApi()
      setApiCatalog({
        title: openapi.info?.title || 'Backend API',
        version: openapi.info?.version || '',
        routes: parseApiCatalog(openapi),
        schemaCount: Object.keys(openapi.components?.schemas || {}).length,
      })
    } catch (e) {
      setApiCatalogError(e.message)
    } finally {
      apiCatalogBusyRef.current = false
      setApiCatalogBusy(false)
    }
  }, [])

  const refreshIntegrationStatus = useCallback(async () => {
    if (integrationStatusBusyRef.current) return
    integrationStatusBusyRef.current = true
    setIntegrationStatusBusy(true)
    setIntegrationStatusError(null)
    try {
      setIntegrationStatus(await fetchIntegrationStatus())
    } catch (e) {
      setIntegrationStatusError(e.message)
    } finally {
      integrationStatusBusyRef.current = false
      setIntegrationStatusBusy(false)
    }
  }, [])

  function openApiPanel() {
    setApiPanelOpen(true)
    refreshApiCatalog()
    refreshIntegrationStatus()
  }

  async function handleCredentialSave(envName) {
    const value = credentialDrafts[envName] || ''
    if (!value.trim()) {
      setCredentialSaveError(`${envName} 为空`)
      setCredentialSaveMessage(null)
      return
    }
    if (!window.confirm(`确认保存 ${envName} 到本地环境配置？`)) return
    setCredentialSaveBusy(envName)
    setCredentialSaveError(null)
    setCredentialSaveMessage(null)
    try {
      await saveIntegrationEnv({ [envName]: value })
      setCredentialDrafts((drafts) => ({ ...drafts, [envName]: '' }))
      setCredentialSaveMessage(`${envName} 已保存`)
      await refreshIntegrationStatus()
    } catch (e) {
      setCredentialSaveError(e.message)
    } finally {
      setCredentialSaveBusy(null)
    }
  }

  function useExample() {
    if (currentScenario?.example) setInput(currentScenario.example)
  }

  function handleHumanConfirm(decision, edits) {
    if (pendingModuleCall) {
      if (decision === 'approve') return approveModuleCall(pendingModuleCall, null)
      if (decision === 'edit') return editModuleCall(pendingModuleCall, edits)
      return rejectModuleCall(pendingModuleCall)
    }
    if (decision === 'approve') return approveTask()
    if (decision === 'edit') return editTask(edits)
    return rejectTask()
  }

  function handleChatSubmit(rawPrompt) {
    const normalized = rawPrompt.trim()
    if (!normalized) return
    setInput(normalized)
    const capabilities = suggestCapabilitiesForInput(normalized, 3)
    dispatchWorkbench({ type: 'add_user_message', text: normalized })
    dispatchWorkbench({ type: 'set_suggestions', capabilities })
    dispatchWorkbench({
      type: 'add_assistant_message',
      text: `已识别意图，推荐 ${capabilities.length} 个能力。需要人工确认后才会执行。`,
    })
    if (capabilities[0]?.workspace) {
      dispatchWorkbench({ type: 'set_workspace', workspace: capabilities[0].workspace })
    }
  }

  function handleCapabilityRequest(capability) {
    const promptText = chatPrompt.trim() || input.trim()
    if (capability.requiresConfirmation) {
      dispatchWorkbench({ type: 'set_pending_confirmation', pendingConfirmation: { capability, prompt: promptText } })
      return
    }
    executeCapability(capability, promptText, {})
  }

  async function handleConfirmCapability(inputValues = {}) {
    const pending = workbenchState.pendingConfirmation
    if (!pending) return
    dispatchWorkbench({ type: 'clear_pending_confirmation' })
    await executeCapability(pending.capability, pending.prompt, inputValues)
  }

  async function executeCapability(capability, promptText, inputValues = {}) {
    const run = createRun(capability)
    dispatchWorkbench({ type: 'start_run', run })
    dispatchWorkbench({ type: 'clear_errors' })
    dispatchWorkbench({ type: 'set_workspace', workspace: capability.workspace })
    try {
      const artifacts = []
      const searchPayload = {
        ...buildSearchPayload(inputValues.query || promptText || input),
        claim: inputValues.claim || promptText || input,
        limit: Number(inputValues.limit || 10),
        service: inputValues.service || undefined,
      }

      if (capability.id === 'search_plan') {
        const plan = await createSearchPlan({ query: searchPayload.query, limit: searchPayload.limit, service: searchPayload.service })
        artifacts.push(createArtifact('search_plan', '搜索计划', plan, capability.id))
      } else if (capability.id === 'search_intel_pipeline') {
        const plan = await createSearchPlan({ query: searchPayload.query, limit: searchPayload.limit, service: searchPayload.service })
        const results = await runSearch({ query: searchPayload.query, limit: searchPayload.limit, service: searchPayload.service })
        const evidence = await createSearchEvidence(searchPayload)
        const brief = await createSearchBrief(searchPayload)
        artifacts.push(
          createArtifact('search_plan', '搜索计划', plan, capability.id),
          createArtifact('search_results', '搜索结果', results, capability.id),
          createArtifact('evidence_records', '证据链', evidence, capability.id),
          createArtifact('intel_brief', '情报简报', brief, capability.id),
        )
        const archiveCapability = getCapabilityById('archive_brief')
        if (archiveCapability) {
          dispatchWorkbench({ type: 'set_suggestions', capabilities: [archiveCapability, ...suggestCapabilitiesForInput(promptText, 2)] })
        }
      } else if (capability.id === 'archive_brief') {
        const latestBrief = latestArtifact(workbenchState.artifacts, 'intel_brief')
        const artifactType = inputValues.artifact_type || (latestBrief ? 'brief' : 'brief')
        const archiveRecord = await archiveSearchArtifact({
          ...searchPayload,
          artifact_type: artifactType,
        })
        artifacts.push(createArtifact('archive_record', '归档记录', archiveRecord, capability.id))
      } else if (capability.id === 'archive_recent') {
        const recent = await fetchRecentArchives({ limit: Number(inputValues.limit || 20) })
        artifacts.push(createArtifact('archive_record', '最近归档', recent, capability.id))
      } else if (capability.id === 'archive_diff') {
        const diff = await fetchArchiveDiff({
          artifact_type: inputValues.artifact_type || undefined,
          watchlist_name: inputValues.watchlist_name || undefined,
        })
        artifacts.push(createArtifact('archive_record', '归档变化', diff, capability.id))
      } else if (capability.id === 'watchlist_run') {
        const items = parseWatchlistItems(inputValues.itemsText || promptText)
        if (!items.length) throw new Error('watchlist items must not be empty')
        const result = await runSearchWatchlist({
          items,
          limit: Number(inputValues.limit || 10),
          archive: inputValues.archive !== false,
          service: inputValues.service || undefined,
        })
        artifacts.push(createArtifact('watchlist_run', 'Watchlist 运行', result, capability.id))
      } else if (capability.id === 'resume_ingest') {
        const [fallbackFilePath, fallbackCandidateId] = promptText.split(/\s+/).filter(Boolean)
        const filePath = inputValues.file_path || fallbackFilePath
        const candidateId = inputValues.candidate_id || fallbackCandidateId
        if (!filePath || !candidateId) throw new Error('请按 “文件路径 candidate_id” 输入。')
        const result = await ingestResume({
          file_path: filePath,
          candidate_id: candidateId,
          write_database: Boolean(inputValues.write_database),
        })
        artifacts.push(createArtifact('resume_ingest', '简历 ingest', result, capability.id))
      } else if (capability.id === 'candidate_match') {
        const result = await matchJobs({ query: inputValues.query || promptText, top_k: Number(inputValues.top_k || 5) })
        artifacts.push(createArtifact('candidate_matches', '候选人匹配', result, capability.id))
      } else if (capability.id === 'rsi_evaluate') {
        const result = await evaluateRsi({
          suite: inputValues.suite || 'candidate_evaluation_core',
          threshold: inputValues.threshold || undefined,
          mode: inputValues.mode || 'local',
          allow_live: Boolean(inputValues.allow_live),
          search_service: inputValues.search_service || undefined,
          llm_service: inputValues.llm_service || 'openrouter_evidence_judge',
        })
        artifacts.push(createArtifact('rsi_report', 'RSI 评估报告', result, capability.id))
      } else if (capability.id === 'workflow_a' || capability.id === 'workflow_b') {
        const scenario = capability.apiCalls[0]?.scenario || 'A'
        const snapshot = await startModule(scenario, inputValues.input || promptText)
        if (snapshot) artifacts.push(createArtifact('workflow_snapshot', `${scenario} 工作流`, snapshot, capability.id))
      } else if (capability.id === 'workflow_atomic') {
        dispatchWorkbench({ type: 'set_workspace', workspace: 'workflow' })
      } else if (capability.id === 'ops_health') {
        await fetchHealth()
        await refreshIntegrationStatus()
      } else if (capability.id === 'ops_env_save') {
        throw new Error('API Key 保存请在 OpsWorkspace 的本地表单中确认执行。')
      } else if (capability.id === 'review_feedback') {
        await fetchReviewFeedback()
      } else {
        throw new Error(`未实现能力执行器：${capability.id}`)
      }

      if (artifacts.length) dispatchWorkbench({ type: 'add_artifacts', artifacts })
      dispatchWorkbench({
        type: 'add_assistant_message',
        capabilityId: capability.id,
        text: `${capability.title} 已完成，生成 ${artifacts.length} 个 artifact。`,
      })
      dispatchWorkbench({ type: 'finish_run', runId: run.id, status: 'done' })
    } catch (e) {
      dispatchWorkbench({ type: 'finish_run', runId: run.id, status: 'error' })
      dispatchWorkbench({ type: 'add_error', capabilityId: capability.id, message: e.message })
      dispatchWorkbench({
        type: 'add_assistant_message',
        capabilityId: capability.id,
        text: `${capability.title} 执行失败：${e.message}`,
      })
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">AI</span>
          <div>
            <div className="brand-title">AI 招聘控制台</div>
            <div className="brand-sub">{isStreaming ? 'SSE 实时事件' : activeTaskId ? '轮询 fallback' : 'REST 控制台'}</div>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            className={`system-chip api-trigger ${metaOnline ? 'chip-online' : 'chip-offline'}`}
            type="button"
            onClick={openApiPanel}
          >
            <span className="chip-dot" />
            {metaOnline ? 'API 在线' : 'API 未连接'}
          </button>
          <button
            className={`run-status status-${taskStatus}`}
            type="button"
            onClick={() => task && setCompletedPanelOpen(true)}
            disabled={!task}
          >
            {statusMeta.name_zh}
            <span className="run-step">{task ? `${doneSteps}/${totalSteps}` : '0/0'}</span>
          </button>
          <button
            className={`system-chip report-trigger ${reportReady ? 'chip-online' : 'chip-offline'}`}
            type="button"
            onClick={() => setReportPageOpen(true)}
            disabled={!reportReady}
          >
            <span className="chip-dot" />
            交付报告
          </button>
        </div>
      </header>

      {reportPageOpen ? (
        <main className="report-page" aria-label="交付报告页">
          <section className="report-page-head">
            <div>
              <div className="section-label">Delivery</div>
              <h1>{reportTitle}</h1>
              <p>
                {task?.task_id || '无任务'} · {currentScenario?.name_zh || currentDisplay.title} · {statusMeta.name_zh}
              </p>
            </div>
            <button className="btn btn-ghost report-back" type="button" onClick={() => setReportPageOpen(false)}>
              返回控制台
            </button>
          </section>
          <section className="report-document">
            <ResultPanel
              task={task}
              teamConstraint={debouncedTeamConstraint}
              apertureWeight={debouncedApertureWeight / 100}
            />
          </section>
        </main>
      ) : (
        <>
      <section className={`workbench-shell ${drawerOpen ? 'drawer-open' : 'drawer-collapsed'}`} aria-label="ChatGPT 式能力工作台">
        <div className="chat-main">
          <ChatShell
            activeRuns={workbenchState.activeRuns}
            busy={busy}
            messages={workbenchState.chatMessages}
            onCancelConfirmation={() => dispatchWorkbench({ type: 'clear_pending_confirmation' })}
            onConfirmCapability={handleConfirmCapability}
            onRequestCapability={handleCapabilityRequest}
            onSubmitPrompt={handleChatSubmit}
            pendingConfirmation={workbenchState.pendingConfirmation}
            prompt={chatPrompt}
            setPrompt={setChatPrompt}
            suggestedCapabilities={workbenchState.suggestedCapabilities}
          />
          {workbenchState.apiErrors.length > 0 && (
            <div className="workbench-error-list" aria-label="API errors">
              {workbenchState.apiErrors.slice(0, 3).map((apiError) => (
                <div className="banner banner-error" key={apiError.id}>
                  {apiError.message}
                </div>
              ))}
            </div>
          )}
        </div>
        <button
          className="drawer-toggle btn btn-ghost"
          type="button"
          onClick={() => setDrawerOpen((open) => !open)}
        >
          {drawerOpen ? '收起能力' : '展开能力'}
        </button>
        {drawerOpen && (
          <CapabilityDrawer
            capabilities={capabilityCatalog}
            currentSuggestions={workbenchState.suggestedCapabilities}
            onRequestCapability={handleCapabilityRequest}
            onSelectWorkspace={(workspace) => dispatchWorkbench({ type: 'set_workspace', workspace })}
            pathProductization={PATH_PRODUCTIZATION}
            selectedWorkspace={selectedWorkspace}
          />
        )}
      </section>

      <WorkspaceTabs
        artifacts={workbenchState.artifacts}
        selectedWorkspace={selectedWorkspace}
        workflowPanel={(
          <section className="workspace-panel-inner" aria-label="WorkflowWorkspace">
      <section className="mission-grid" aria-label="运行概览">
        <div className="metric-card metric-primary">
          <span className="metric-label">当前场景</span>
          <strong>{currentDisplay.title}</strong>
          <span>{currentDisplay.description}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">当前阶段</span>
          <strong>{activeNode?.label || '待启动'}</strong>
          <span>{activeNode?.agent?.name_zh || currentScenario?.name_zh || '等待输入'}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">审计事件</span>
          <strong>{auditEvents.length}</strong>
          <span>{activeTaskId || '无任务'}</span>
        </div>
        <div className={`metric-card metric-status status-${taskStatus}`}>
          <span className="metric-label">运行状态</span>
          <strong>{statusMeta.name_zh}</strong>
          <span>{statusMeta.help}</span>
        </div>
      </section>

      <section className="aperture-control" aria-label="招聘决策约束">
        <div className="aperture-copy">
          <div className="section-label">Decision Constraints</div>
          <h2>招聘决策约束</h2>
          <p>约束项：{debouncedTeamConstraint} · 权重 {debouncedApertureWeight}%</p>
        </div>
        <div className="aperture-fields">
          <label className="field-label" htmlFor="team-constraint">核心筛选条件</label>
          <input
            id="team-constraint"
            className="aperture-input"
            value={teamConstraint}
            onChange={(event) => setTeamConstraint(event.target.value)}
            placeholder="真机泛化、动作延迟、数据闭环"
          />
        </div>
        <div className="aperture-slider">
          <div className="slider-head">
            <span>筛选权重</span>
            <strong>{apertureWeight}</strong>
          </div>
          <input
            type="range"
            min="10"
            max="100"
            step="5"
            value={apertureWeight}
            onChange={(event) => setApertureWeight(Number(event.target.value))}
            aria-label="筛选权重"
          />
        </div>
      </section>

      {error && <div className="banner banner-error">{error}</div>}

      <ModuleGraph
        activeModuleId={activeModuleId}
        context={agentContext}
        disabled={Boolean(running || busy)}
        moduleStatuses={moduleStatuses}
        onDismissCall={dismissModuleCall}
        onRequestCall={requestModuleCall}
        onSelectModule={setCurrentScenarioId}
        pendingCall={pendingModuleCall}
        recommendedCalls={recommendedModuleCalls}
      />

      <section className="control-plane">
        <section className="scenario-box" aria-label="招聘场景">
          <div className="scenario-box-head">
            <span className="section-label">Capabilities</span>
            <span>{scenarios.length ? `${scenarios.length} 个能力` : '未连接'}</span>
          </div>
          <nav className="scenario-rail">
            {scenarios.map((scenario) => {
              const display = SCENARIO_DISPLAY[scenario.id] || {
                title: scenario.name_zh?.replace(/^场景\s*[A-Z]：/, '') || scenario.id,
                description: scenario.input_hint || '',
              }
              return (
                <button
                  key={scenario.id}
                  className={`scenario-card ${scenario.id === currentScenarioId ? 'scenario-active' : ''}`}
                  onClick={() => setCurrentScenarioId(scenario.id)}
                  disabled={running}
                >
                  <span className="scenario-id">{scenario.id}</span>
                  <span className="scenario-copy">
                    <span className="scenario-name">{display.title}</span>
                    <span className="scenario-meta">{display.description}</span>
                  </span>
                </button>
              )
            })}
          </nav>
        </section>

        <div className="command-deck">
          <div className="command-head">
            <div>
              <div className="section-label">Task Launch</div>
              <h1>{currentDisplay.title}</h1>
              <p>{currentScenario?.input_hint || '等待后端协议。'}</p>
            </div>
            <div className="step-counter" aria-label="当前进度">
              <span>{doneSteps}</span>
              <small>/ {totalSteps}</small>
            </div>
          </div>

          <label className="field-label" htmlFor="agent-input">招聘目标</label>
          <textarea
            id="agent-input"
            className="composer-input"
            placeholder={currentScenario?.input_hint || '输入招聘任务'}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            rows={4}
            disabled={running}
          />
          <div className="composer-actions">
            <button className="btn btn-ghost" onClick={useExample} disabled={running || !currentScenario?.example}>
              使用样例
            </button>
            {running && (
              <button className="btn btn-reject" onClick={cancelTask} disabled={busy}>
                取消任务
              </button>
            )}
            <button className="btn btn-run" onClick={() => startModule(currentScenarioId, input)} disabled={busy || running || !input.trim() || !currentScenario}>
              {running ? '执行中' : '启动任务'}
            </button>
          </div>
        </div>
      </section>

      <AtomicWorkflowPanel
        apertureWeight={debouncedApertureWeight / 100}
        disabled={Boolean(running || busy)}
        input={input}
        scenario={currentScenario}
        scenarioId={currentScenarioId}
        teamConstraint={debouncedTeamConstraint}
      />

      {task && (
        <div className="progress-wrap" aria-label="任务进度">
          <div className="progress-copy">
            <span>{statusMeta.name_zh}</span>
            <span>{progress}%</span>
          </div>
          <div className="progress-track">
            <div className={`progress-fill status-${task.status}`} style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <LiveTaskSummary task={task} agentNodes={agentNodes} />

      {pendingModuleCall && pendingModuleAwaiting && (
        <section className="hitl-priority-panel" aria-label="跨模块调用确认">
          <HumanGate awaiting={pendingModuleAwaiting} busy={busy} onConfirm={handleHumanConfirm} />
        </section>
      )}

      {!pendingModuleCall && task?.status === 'awaiting_human' && task.awaiting && (
        <section className="hitl-priority-panel" aria-label="人工确认">
          <HumanGate awaiting={task.awaiting} busy={busy} onConfirm={handleHumanConfirm} />
        </section>
      )}

      <main className={`workspace ${task?.scenario === 'C' && task?.status === 'done' ? 'workspace-sandbox' : ''}`}>
        <section className="col col-flow">
          <div className="col-head">
            <div>
              <div className="col-title">执行链路</div>
              <p>{activeNode ? `${activeNode.agent?.name_zh || activeNode.agent_id} · ${activeNode.status}` : `${totalSteps} steps`}</p>
            </div>
            <span className="panel-index">{totalSteps} steps</span>
          </div>
          {agentNodes.length ? <AgentFlow nodes={agentNodes} /> : <div className="result-empty">等待场景协议。</div>}
        </section>

        <aside className="col col-side">
          <SharedContextPanel context={agentContext} moduleHistory={moduleHistory} />
          <LogStream logs={task?.logs} />
          <div className={`report-launcher ${reportReady ? 'report-ready' : ''}`}>
            <div className="report-launcher-head">
              <div>
                <div className="col-title">交付报告</div>
                <p>{reportReady ? reportTitle : task?.status || '未生成'}</p>
              </div>
              <span>{reportReady ? `${task.result?.human_report?.citations?.length || 0} 证据` : '未生成'}</span>
            </div>
            <p>
              交付项：分析正文、证据引用、结构化结果。
            </p>
            <button className="btn btn-run" type="button" onClick={() => setReportPageOpen(true)} disabled={!reportReady}>
              {reportReady ? '打开报告' : '未生成'}
            </button>
          </div>
        </aside>
      </main>
          </section>
        )}
        opsPanel={(
          <section className="workspace-panel-inner ops-workspace" aria-label="OpsWorkspace">
            <div className="workspace-panel-head">
              <div>
                <span className="section-label">OpsWorkspace</span>
                <h2>运维状态</h2>
              </div>
              <button className="btn btn-ghost" type="button" onClick={openApiPanel}>
                打开 API 面板
              </button>
            </div>
            <div className="ops-grid">
              <div className={`ops-card ${metaOnline ? 'ops-ready' : 'ops-error'}`}>
                <span>health</span>
                <strong>{metaOnline ? '在线' : '未连接'}</strong>
                <p>{activeTaskId || '无任务运行'}</p>
              </div>
              <div className="ops-card">
                <span>integrations</span>
                <strong>{integrationStatus ? `${integrationStatus.capabilities.length} capabilities` : '未读取'}</strong>
                <p>{integrationStatus?.config_path || 'config/services.toml'}</p>
              </div>
              <div className="ops-card">
                <span>api catalog</span>
                <strong>{apiCatalog ? `${apiCatalog.routes.length} routes` : '未读取'}</strong>
                <p>{API_DOCS_URL}</p>
              </div>
            </div>
            <div className="ops-actions">
              <button className="btn btn-run" type="button" onClick={refreshIntegrationStatus} disabled={integrationStatusBusy}>
                {integrationStatusBusy ? '读取中' : '刷新集成状态'}
              </button>
              <button className="btn btn-ghost" type="button" onClick={refreshApiCatalog} disabled={apiCatalogBusy}>
                {apiCatalogBusy ? '读取中' : '刷新 API Catalog'}
              </button>
            </div>
          </section>
        )}
      />
        </>
      )}

      {apiPanelOpen && (
        <div className="api-overlay" role="dialog" aria-modal="true" aria-labelledby="api-panel-title">
          <div className="api-panel">
            <div className="api-panel-head">
              <div>
                <div className="section-label">Backend API</div>
                <h2 id="api-panel-title">后端 API 清单</h2>
                <p>来自 `/openapi.json` 与 `/integrations/status`。</p>
              </div>
              <button className="btn btn-ghost api-close" type="button" onClick={() => setApiPanelOpen(false)}>
                关闭
              </button>
            </div>

            <div className="api-panel-meta">
              <span>{apiCatalog?.title || 'Robot Talent Agent MVP'}</span>
              <span>{apiCatalog?.version ? `v${apiCatalog.version}` : 'version unknown'}</span>
              <span>{apiCatalog ? `${apiCatalog.routes.length} routes` : 'loading routes'}</span>
              <span>{apiCatalog ? `${apiCatalog.schemaCount} schemas` : 'loading schemas'}</span>
              <span>{integrationStatus ? `${integrationStatus.capabilities.length} capabilities` : 'loading capabilities'}</span>
              <a className="api-doc-link" href={API_DOCS_URL} target="_blank" rel="noreferrer">打开 Swagger</a>
            </div>

            <section className="integration-section" aria-label="后端 API 接入状态">
              <div className="api-section-head">
                <div>
                  <h3>API 接入</h3>
                  <p>{integrationStatus?.config_path || 'config/services.toml'}</p>
                </div>
              </div>
              {integrationStatusBusy && <div className="api-state integration-state">读取中。</div>}
              {integrationStatusError && <div className="api-state api-state-error integration-state">读取失败：{integrationStatusError}</div>}
              {integrationStatus && (
                <>
                  <div className="credential-grid" aria-label="环境变量保存">
                    {integrationCredentialRows(integrationStatus).map((credential) => (
                      <div className={`credential-row ${credential.present ? 'credential-ready' : ''}`} key={credential.env}>
                        <div className="credential-meta">
                          <strong>{credential.env}</strong>
                          <span>{credential.present ? '已保存' : '未保存'} · {credential.services.slice(0, 2).join(' / ')}</span>
                        </div>
                        <input
                          type="password"
                          value={credentialDrafts[credential.env] || ''}
                          onChange={(event) => setCredentialDrafts((drafts) => ({ ...drafts, [credential.env]: event.target.value }))}
                          placeholder="粘贴 key"
                          autoComplete="off"
                        />
                        <button
                          className="btn btn-run credential-save"
                          type="button"
                          onClick={() => handleCredentialSave(credential.env)}
                          disabled={credentialSaveBusy === credential.env}
                        >
                          {credentialSaveBusy === credential.env ? '保存中' : '保存'}
                        </button>
                      </div>
                    ))}
                  </div>
                  {credentialSaveError && <div className="api-state api-state-error integration-state">保存失败：{credentialSaveError}</div>}
                  {credentialSaveMessage && <div className="api-state integration-state">{credentialSaveMessage}</div>}
                  <div className="integration-grid">
                    {integrationStatus.capabilities.map((capability) => {
                      const tone = integrationStatusTone(capability.status)
                      return (
                        <article className={`integration-card tone-${tone}`} key={capability.id}>
                          <div className="integration-card-head">
                            <span className="integration-dot" />
                            <strong>{capability.label || capability.id}</strong>
                            <span className="integration-pill">{integrationStatusLabel(capability.status)}</span>
                          </div>
                          <div className="integration-fields">
                            <span>标题名字</span>
                            <strong>{capability.label || capability.id}</strong>
                            <span>有无接入</span>
                            <strong>{integrationStatusLabel(capability.status)}</strong>
                            <span>接入中文名</span>
                            <strong>{capability.connected_name_zh || capability.name_zh || '未接入'}</strong>
                            <span>代码路径</span>
                            <code>{capability.code_path || '未接入'}</code>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </>
              )}
            </section>

            {apiCatalogBusy && <div className="api-state">读取中。</div>}
            {apiCatalogError && <div className="api-state api-state-error">读取失败：{apiCatalogError}</div>}
            {apiCatalog && (
              <div className="api-route-list">
                {apiCatalog.routes.map((route) => (
                  <article className="api-route" key={`${route.method}-${route.path}`}>
                    <div className="api-route-main">
                      <span className={`api-method method-${route.method.toLowerCase()}`}>{route.method}</span>
                      <code>{route.path}</code>
                    </div>
                    <div className="api-route-copy">
                      <strong>{route.summary}</strong>
                      {route.description && <span>{route.description}</span>}
                      <span>
                        {route.hasBody ? '需要 request body' : '无 request body'}
                        {route.parameters.length ? ` · ${route.parameters.length} 个参数` : ''}
                        {route.responses.length ? ` · 响应 ${route.responses.join('/')}` : ''}
                      </span>
                      {route.operationId && <small>{route.operationId}</small>}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {completedPanelOpen && task && (
        <div className="api-overlay" role="dialog" aria-modal="true" aria-labelledby="completed-panel-title">
          <div className="api-panel completed-panel">
            <div className="api-panel-head">
              <div>
                <div className="section-label">Task Steps</div>
                <h2 id="completed-panel-title">已完成步骤</h2>
                <p>{task.task_id}</p>
              </div>
              <button className="btn btn-ghost api-close" type="button" onClick={() => setCompletedPanelOpen(false)}>
                关闭
              </button>
            </div>
            <div className="api-panel-meta">
              <span>{currentScenario?.name_zh || task.scenario}</span>
              <span>{task.status}</span>
              <span>{task.steps_done?.length || 0}/{task.total_steps} done</span>
              <span>{auditEvents.length} events</span>
            </div>
            {(!task.steps_done || task.steps_done.length === 0) && <div className="api-state">暂无完成步骤。</div>}
            {task.steps_done?.length > 0 && (
              <div className="completed-list">
                {task.steps_done.map((doneStep, index) => {
                  const node = agentNodes[index]
                  return (
                    <article className="completed-step" key={`${doneStep.agent_id || 'step'}-${index}`}>
                      <div className="completed-step-head">
                        <span className="flow-dot">{String(index + 1).padStart(2, '0')}</span>
                        <div>
                          <strong>{doneStep.label || node?.label || `步骤 ${index + 1}`}</strong>
                          <span>{node?.agent?.name_zh || doneStep.agent_id || '未知 Agent'}</span>
                        </div>
                      </div>
                      <div className="completed-output">
                        <JsonView value={doneStep.output} />
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
