import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelTask as requestCancelTask,
  confirmTask,
  fetchMeta,
  fetchTask,
  runScenario,
  taskStreamUrl,
} from '../api.js'

const TERMINAL_STATUS = new Set(['done', 'error', 'cancelled'])
const STREAM_EVENTS = ['step_start', 'tool_call', 'evidence', 'summary', 'human_gate', 'error', 'cancelled']

const STATUS_FALLBACK = {
  idle: { name_zh: '未运行', help: '等待任务启动。' },
  processing: { name_zh: '执行中', help: 'AgentRunner 正在处理当前节点。' },
  awaiting_human: { name_zh: '等待人工确认', help: '流程暂停在人工门控。' },
  done: { name_zh: '已完成', help: '报告已生成。' },
  error: { name_zh: '已终止', help: '任务异常结束。' },
  cancelled: { name_zh: '已取消', help: '任务已取消。' },
}

function mergeEvents(prev, event) {
  if (!event?.id) return prev
  if (prev.some((item) => item.id === event.id)) return prev
  return [...prev, event].sort((a, b) => Number(a.id) - Number(b.id))
}

function eventToLog(event) {
  const level =
    event.type === 'human_gate'
      ? 'hitl'
      : event.type === 'error' || event.type === 'cancelled'
        ? 'error'
        : event.status === 'done'
          ? 'done'
          : 'info'
  return {
    ts: event.created_at,
    agent: event.agent_id || 'orchestrator',
    message: event.message || '',
    level,
    event_type: event.type,
  }
}

function mergeLogs(prev, event) {
  if (!event?.id) return prev
  if (prev.some((item) => item.event_id === event.id)) return prev
  return [...prev, { ...eventToLog(event), event_id: event.id }]
}

function mergeStepDone(stepsDone, event) {
  const stepDone = event?.data?.step_done
  if (!stepDone) return stepsDone || []
  const exists = (stepsDone || []).some(
    (item) => item.agent_id === stepDone.agent_id && item.label === stepDone.label,
  )
  if (exists) return stepsDone || []
  return [...(stepsDone || []), stepDone]
}

function applyEventToTask(task, event) {
  if (!task) return task
  const next = {
    ...task,
    audit_events: mergeEvents(task.audit_events || [], event),
    logs: mergeLogs(task.logs || [], event),
  }
  if (event.status) next.status = event.status
  if (event.agent_id) next.current_agent = event.agent_id
  if (Number.isInteger(event.step_index)) next.current_step = event.step_index

  if (event.type === 'summary') {
    next.steps_done = mergeStepDone(next.steps_done || [], event)
    if (event.data?.result) next.result = event.data.result
  }
  if (event.type === 'human_gate') {
    if (event.data?.awaiting) next.awaiting = event.data.awaiting
    if (event.data?.decision) next.awaiting = null
  }
  if (event.type === 'error' || event.type === 'cancelled') {
    next.error = event.message
    next.awaiting = null
  }
  return next
}

function buildAgentNodes(currentScenario, agents, task, auditEvents) {
  const steps = currentScenario?.steps || []
  const touched = new Map()
  for (const event of auditEvents || []) {
    if (!Number.isInteger(event.step_index)) continue
    const current = touched.get(event.step_index) || {}
    if (event.type === 'step_start') current.status = 'active'
    if (event.type === 'summary') {
      current.status = 'done'
      current.output = event.data?.output ?? current.output
    }
    if (event.type === 'human_gate' && event.data?.awaiting) current.status = 'awaiting'
    if (event.type === 'human_gate' && event.data?.decision) current.status = 'done'
    if (event.type === 'error' || event.type === 'cancelled') current.status = 'error'
    touched.set(event.step_index, current)
  }

  return steps.map((step, index) => {
    const state = touched.get(index) || {}
    let status = task ? 'pending' : 'idle'
    if (state.status) status = state.status
    if (task?.status === 'done') status = 'done'
    if ((task?.status === 'error' || task?.status === 'cancelled') && task.current_step === index) status = 'error'
    return {
      ...step,
      index,
      status,
      output: state.output ?? task?.steps_done?.[index]?.output,
      agent: agents?.[step.agent_id] || {},
    }
  })
}

export function useAgentOrchestrator() {
  const [meta, setMeta] = useState(null)
  const [currentScenarioId, setCurrentScenarioId] = useState('')
  const [activeTaskId, setActiveTaskId] = useState(null)
  const [task, setTask] = useState(null)
  const [taskStatus, setTaskStatus] = useState('idle')
  const [auditEvents, setAuditEvents] = useState([])
  const [report, setReport] = useState(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [teamConstraint, setTeamConstraint] = useState('真机泛化')
  const [apertureWeight, setApertureWeight] = useState(70)
  const [debouncedTeamConstraint, setDebouncedTeamConstraint] = useState('真机泛化')
  const [debouncedApertureWeight, setDebouncedApertureWeight] = useState(70)

  const sourceRef = useRef(null)
  const pollRef = useRef(null)
  const statusRef = useRef('idle')
  const activeTaskRef = useRef(null)

  const scenarios = useMemo(() => meta?.scenarios || [], [meta?.scenarios])
  const agents = useMemo(() => meta?.agents || {}, [meta?.agents])
  const taskStatuses = meta?.task_statuses || STATUS_FALLBACK
  const currentScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === currentScenarioId) || scenarios[0] || null,
    [currentScenarioId, scenarios],
  )
  const agentNodes = useMemo(
    () => buildAgentNodes(currentScenario, agents, task, auditEvents),
    [currentScenario, agents, task, auditEvents],
  )

  useEffect(() => {
    statusRef.current = taskStatus
  }, [taskStatus])

  useEffect(() => {
    activeTaskRef.current = activeTaskId
  }, [activeTaskId])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedTeamConstraint(teamConstraint.trim() || '真机泛化')
      setDebouncedApertureWeight(apertureWeight)
    }, 350)
    return () => window.clearTimeout(timer)
  }, [teamConstraint, apertureWeight])

  useEffect(() => {
    let alive = true
    async function loadMeta() {
      try {
        const data = await fetchMeta()
        if (!alive) return
        setMeta(data)
        setError(null)
        setCurrentScenarioId((prev) => {
          if (prev && data.scenarios?.some((scenario) => scenario.id === prev)) return prev
          return data.scenarios?.[0]?.id || ''
        })
      } catch (e) {
        if (alive) setError(e.message)
      }
    }
    loadMeta()
    const interval = window.setInterval(loadMeta, 5000)
    return () => {
      alive = false
      window.clearInterval(interval)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const stopStream = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close()
      sourceRef.current = null
    }
    setIsStreaming(false)
  }, [])

  const applySnapshot = useCallback((snapshot) => {
    setTask(snapshot)
    setActiveTaskId(snapshot?.task_id || null)
    setTaskStatus(snapshot?.status || 'idle')
    setAuditEvents(snapshot?.audit_events || [])
    setReport(snapshot?.result || null)
    setError(snapshot?.status === 'error' || snapshot?.status === 'cancelled' ? snapshot.error || null : null)
  }, [])

  const refreshTask = useCallback(
    async (taskId) => {
      const snapshot = await fetchTask(taskId)
      applySnapshot(snapshot)
      if (TERMINAL_STATUS.has(snapshot.status)) {
        stopPolling()
        stopStream()
      }
      return snapshot
    },
    [applySnapshot, stopPolling, stopStream],
  )

  const startPolling = useCallback(
    (taskId) => {
      stopPolling()
      pollRef.current = window.setInterval(async () => {
        try {
          const snapshot = await refreshTask(taskId)
          if (TERMINAL_STATUS.has(snapshot.status)) stopPolling()
        } catch (e) {
          setError(e.message)
          stopPolling()
        }
      }, 600)
    },
    [refreshTask, stopPolling],
  )

  const handleEvent = useCallback(
    (event, taskId) => {
      setAuditEvents((prev) => mergeEvents(prev, event))
      setTask((prev) => applyEventToTask(prev, event))
      if (event.status) setTaskStatus(event.status)
      if (event.data?.result) {
        setReport(event.data.result)
      }
      if (event.type === 'error' || event.type === 'cancelled') {
        setError(event.message)
      } else if (event.status !== 'error' && event.status !== 'cancelled') {
        setError(null)
      }
      if (event.status && TERMINAL_STATUS.has(event.status)) {
        refreshTask(taskId).catch((e) => setError(e.message))
      }
    },
    [refreshTask],
  )

  const subscribeTaskStream = useCallback(
    (taskId) => {
      stopStream()
      stopPolling()
      if (!window.EventSource) {
        startPolling(taskId)
        return null
      }
      const source = new EventSource(taskStreamUrl(taskId))
      sourceRef.current = source
      startPolling(taskId)
      source.onopen = () => {
        setIsStreaming(true)
        setError(null)
      }
      for (const eventName of STREAM_EVENTS) {
        source.addEventListener(eventName, (message) => {
          try {
            const event = JSON.parse(message.data)
            handleEvent(event, taskId)
            if (event.status && TERMINAL_STATUS.has(event.status)) {
              source.close()
              sourceRef.current = null
              setIsStreaming(false)
            }
          } catch (e) {
            setError(e.message)
          }
        })
      }
      source.onerror = () => {
        source.close()
        sourceRef.current = null
        setIsStreaming(false)
        if (!TERMINAL_STATUS.has(statusRef.current)) {
          startPolling(taskId)
        }
      }
      return source
    },
    [handleEvent, startPolling, stopPolling, stopStream],
  )

  const startTask = useCallback(
    async (input, scenarioIdOverride = null) => {
      const scenarioToRun = scenarioIdOverride
        ? scenarios.find((scenario) => scenario.id === scenarioIdOverride) || currentScenario
        : currentScenario
      if (!scenarioToRun?.id || !input.trim()) return null
      setBusy(true)
      setError(null)
      try {
        const created = await runScenario(scenarioToRun.id, input.trim(), {
          teamConstraint: debouncedTeamConstraint,
          apertureWeight: debouncedApertureWeight / 100,
        })
        const snapshot = await fetchTask(created.task_id)
        applySnapshot(snapshot)
        subscribeTaskStream(created.task_id)
        return snapshot
      } catch (e) {
        setError(e.message)
        return null
      } finally {
        setBusy(false)
      }
    },
    [applySnapshot, currentScenario, debouncedApertureWeight, debouncedTeamConstraint, scenarios, subscribeTaskStream],
  )

  const cancelTask = useCallback(async () => {
    if (!activeTaskRef.current) return null
    setBusy(true)
    try {
      const snapshot = await requestCancelTask(activeTaskRef.current)
      applySnapshot(snapshot)
      stopPolling()
      stopStream()
      return snapshot
    } catch (e) {
      setError(e.message)
      return null
    } finally {
      setBusy(false)
    }
  }, [applySnapshot, stopPolling, stopStream])

  const submitHumanGate = useCallback(
    async (decision, edits = null) => {
      if (!activeTaskRef.current) return null
      setBusy(true)
      setError(null)
      try {
        const snapshot = await confirmTask(activeTaskRef.current, decision, edits)
        applySnapshot(snapshot)
        if (!TERMINAL_STATUS.has(snapshot.status)) subscribeTaskStream(snapshot.task_id)
        return snapshot
      } catch (e) {
        setError(e.message)
        return null
      } finally {
        setBusy(false)
      }
    },
    [applySnapshot, subscribeTaskStream],
  )

  const approveTask = useCallback(() => submitHumanGate('approve'), [submitHumanGate])
  const editTask = useCallback((edits) => submitHumanGate('edit', edits), [submitHumanGate])
  const rejectTask = useCallback(() => submitHumanGate('reject'), [submitHumanGate])

  const selectScenario = useCallback((id) => {
    if (task && !TERMINAL_STATUS.has(task.status)) return
    setCurrentScenarioId(id)
    setTask(null)
    setActiveTaskId(null)
    setTaskStatus('idle')
    setAuditEvents([])
    setReport(null)
    setError(null)
  }, [task])

  useEffect(() => () => {
    stopPolling()
    stopStream()
  }, [stopPolling, stopStream])

  return {
    meta,
    scenarios,
    currentScenario,
    currentScenarioId,
    setCurrentScenarioId: selectScenario,
    activeTaskId,
    task,
    taskStatus,
    taskStatuses,
    agentNodes,
    auditEvents,
    report,
    isStreaming,
    error,
    busy,
    apertureWeight,
    setApertureWeight,
    teamConstraint,
    setTeamConstraint,
    debouncedApertureWeight,
    debouncedTeamConstraint,
    startTask,
    cancelTask,
    approveTask,
    editTask,
    rejectTask,
    subscribeTaskStream,
    refreshTask,
  }
}
