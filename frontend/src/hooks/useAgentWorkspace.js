import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AGENT_EVENTS } from '../agent/agentEvents.js'
import { MODULE_SEQUENCE, getModule } from '../agent/moduleGraph.js'
import {
  buildDirectModuleInput,
  buildModuleInput,
  createInitialAgentContext,
  createModuleCall,
  getRecommendedModuleCalls,
  mergeModuleOutput,
} from '../agent/sharedContext.js'
import { useAgentOrchestrator } from './useAgentOrchestrator.js'

const TERMINAL_STATUS = new Set(['done', 'error', 'cancelled'])

function createWorkspaceEvent(type, payload = {}) {
  return {
    id: `${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type,
    createdAt: new Date().toISOString(),
    ...payload,
  }
}

export function useAgentWorkspace() {
  const orchestrator = useAgentOrchestrator()
  const [activeModuleId, setActiveModuleId] = useState('A')
  const [agentContext, setAgentContext] = useState(() => createInitialAgentContext())
  const [pendingModuleCall, setPendingModuleCall] = useState(null)
  const [recommendedModuleCalls, setRecommendedModuleCalls] = useState([])
  const [moduleHistory, setModuleHistory] = useState([])
  const [workspaceEvents, setWorkspaceEvents] = useState([])
  const completedTaskIdsRef = useRef(new Set())

  const appendWorkspaceEvent = useCallback((type, payload = {}) => {
    const event = createWorkspaceEvent(type, payload)
    setWorkspaceEvents((prev) => [...prev, event])
    return event
  }, [])

  const running = orchestrator.task && !TERMINAL_STATUS.has(orchestrator.task.status)

  const setWorkspaceModule = useCallback(
    (moduleId) => {
      if (!moduleId || running) return
      setActiveModuleId(moduleId)
      setPendingModuleCall(null)
      setRecommendedModuleCalls([])
      orchestrator.setCurrentScenarioId(moduleId)
      appendWorkspaceEvent(AGENT_EVENTS.MODULE_SELECTED, { moduleId })
    },
    [appendWorkspaceEvent, orchestrator, running],
  )

  const startModule = useCallback(
    async (moduleId, rawInput) => {
      const normalizedInput = rawInput?.trim() || ''
      if (!moduleId || !normalizedInput || running) return null

      const contextForInput = {
        ...agentContext,
        goal: agentContext.goal || normalizedInput,
        selectedModules: agentContext.selectedModules.includes(moduleId)
          ? agentContext.selectedModules
          : [...agentContext.selectedModules, moduleId],
      }
      const moduleInput = buildDirectModuleInput({
        moduleId,
        rawInput: normalizedInput,
        context: contextForInput,
      })

      setActiveModuleId(moduleId)
      setPendingModuleCall(null)
      setRecommendedModuleCalls([])
      setAgentContext(contextForInput)
      appendWorkspaceEvent(AGENT_EVENTS.MODULE_STARTED, { moduleId })
      orchestrator.setCurrentScenarioId(moduleId)
      return orchestrator.startTask(moduleInput, moduleId)
    },
    [agentContext, appendWorkspaceEvent, orchestrator, running],
  )

  const approveModuleCall = useCallback(
    async (call = pendingModuleCall, edits = null) => {
      if (!call || running) return null
      const moduleInput = buildModuleInput({
        from: call.from,
        to: call.to,
        context: agentContext,
        edits,
      })

      setPendingModuleCall(null)
      setRecommendedModuleCalls([])
      setActiveModuleId(call.to)
      setAgentContext((prev) => ({
        ...prev,
        pendingTransfers: (prev.pendingTransfers || []).filter((item) => item.id !== call.id),
      }))
      appendWorkspaceEvent(AGENT_EVENTS.MODULE_CALL_APPROVED, {
        from: call.from,
        to: call.to,
        riskLevel: call.riskLevel,
      })
      orchestrator.setCurrentScenarioId(call.to)
      return orchestrator.startTask(moduleInput, call.to)
    },
    [agentContext, appendWorkspaceEvent, orchestrator, pendingModuleCall, running],
  )

  const requestModuleCall = useCallback(
    (from, to) => {
      if (running) return null
      const call = createModuleCall({ from, to, context: agentContext })
      if (!call) return null

      appendWorkspaceEvent(AGENT_EVENTS.MODULE_CALL_REQUESTED, {
        from,
        to,
        riskLevel: call.riskLevel,
      })

      if (call.riskLevel === 'low') {
        approveModuleCall(call)
        return call
      }

      setPendingModuleCall(call)
      setAgentContext((prev) => ({
        ...prev,
        pendingTransfers: [...(prev.pendingTransfers || []), call],
      }))
      appendWorkspaceEvent(AGENT_EVENTS.HUMAN_APPROVAL_REQUIRED, { from, to, riskLevel: call.riskLevel })
      return call
    },
    [agentContext, appendWorkspaceEvent, approveModuleCall, running],
  )

  const editModuleCall = useCallback(
    (call = pendingModuleCall, edits = null) => approveModuleCall(call, edits),
    [approveModuleCall, pendingModuleCall],
  )

  const rejectModuleCall = useCallback(
    (call = pendingModuleCall) => {
      if (!call) return null
      setPendingModuleCall(null)
      setAgentContext((prev) => ({
        ...prev,
        pendingTransfers: (prev.pendingTransfers || []).filter((item) => item.id !== call.id),
      }))
      appendWorkspaceEvent(AGENT_EVENTS.MODULE_CALL_REJECTED, {
        from: call.from,
        to: call.to,
        riskLevel: call.riskLevel,
      })
      return call
    },
    [appendWorkspaceEvent, pendingModuleCall],
  )

  const dismissModuleCall = useCallback(
    (call) => {
      if (!call) return null
      setRecommendedModuleCalls((prev) => prev.filter((item) => item.from !== call.from || item.to !== call.to))
      appendWorkspaceEvent(AGENT_EVENTS.MODULE_CALL_REJECTED, {
        from: call.from,
        to: call.to,
        riskLevel: call.riskLevel,
        dismissed: true,
      })
      return call
    },
    [appendWorkspaceEvent],
  )

  useEffect(() => {
    const completedTask = orchestrator.task
    if (!completedTask || completedTask.status !== 'done' || !completedTask.task_id) return
    if (completedTaskIdsRef.current.has(completedTask.task_id)) return
    completedTaskIdsRef.current.add(completedTask.task_id)

    const moduleId = completedTask.scenario || activeModuleId || orchestrator.currentScenarioId
    const nextContext = mergeModuleOutput(
      agentContext,
      moduleId,
      completedTask.result,
      completedTask.steps_done || [],
      completedTask.task_id,
    )

    setAgentContext(nextContext)
    setModuleHistory((prev) => [
      ...prev,
      {
        moduleId,
        moduleTitle: getModule(moduleId)?.title || moduleId,
        taskId: completedTask.task_id,
        result: completedTask.result,
        stepsDone: completedTask.steps_done || [],
        completedAt: new Date().toISOString(),
      },
    ])
    setRecommendedModuleCalls(getRecommendedModuleCalls(nextContext, moduleId))
    appendWorkspaceEvent(AGENT_EVENTS.MODULE_COMPLETED, { moduleId, taskId: completedTask.task_id })
    appendWorkspaceEvent(AGENT_EVENTS.CONTEXT_UPDATED, { moduleId, taskId: completedTask.task_id })
  }, [
    activeModuleId,
    agentContext,
    appendWorkspaceEvent,
    orchestrator.currentScenarioId,
    orchestrator.task,
  ])

  const moduleStatuses = useMemo(() => {
    const completed = new Set(moduleHistory.map((item) => item.moduleId))
    return Object.fromEntries(
      MODULE_SEQUENCE.map((moduleId) => {
        let status = completed.has(moduleId) ? 'done' : 'idle'
        if (activeModuleId === moduleId && orchestrator.task?.status && !TERMINAL_STATUS.has(orchestrator.task.status)) {
          status = orchestrator.task.status === 'awaiting_human' ? 'awaiting' : 'active'
        }
        if (pendingModuleCall?.to === moduleId) status = 'awaiting'
        return [moduleId, status]
      }),
    )
  }, [activeModuleId, moduleHistory, orchestrator.task, pendingModuleCall])

  const pendingModuleAwaiting = useMemo(() => {
    if (!pendingModuleCall) return null
    const fromModule = getModule(pendingModuleCall.from)
    const toModule = getModule(pendingModuleCall.to)
    return {
      prompt: `是否允许「${fromModule?.title || pendingModuleCall.from}」调用「${toModule?.title || pendingModuleCall.to}」？`,
      draft: {
        title: pendingModuleCall.title,
        reason: pendingModuleCall.reason,
        riskLevel: pendingModuleCall.riskLevel,
        reusableInputs: pendingModuleCall.reusableInputs,
        missingInputs: pendingModuleCall.missingInputs,
      },
    }
  }, [pendingModuleCall])

  return {
    ...orchestrator,
    activeModuleId,
    agentContext,
    moduleHistory,
    moduleStatuses,
    pendingModuleAwaiting,
    pendingModuleCall,
    recommendedModuleCalls,
    workspaceEvents,
    approveModuleCall,
    dismissModuleCall,
    editModuleCall,
    rejectModuleCall,
    requestModuleCall,
    setCurrentScenarioId: setWorkspaceModule,
    setWorkspaceModule,
    startModule,
  }
}
