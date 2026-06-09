import { getModule } from './moduleGraph.js'

export const ARTIFACT_LABELS = {
  role_profile: '岗位画像',
  jd: 'JD',
  competency_matrix: '能力矩阵',
  interview_questions: '面试题',
  target_companies: '目标公司',
  sourcing_keywords: '搜索关键词',
  outreach_strategy: '触达策略',
  candidate_scorecard: '候选评分卡',
  evidence_chain: '证据链',
  follow_up_questions: '追问问题',
  weekly_summary: '周报摘要',
  risks: '风险',
  next_actions: '下周动作',
  sourcing_progress: '寻访进展',
}

export const INITIAL_AGENT_CONTEXT = createInitialAgentContext()

export function createInitialAgentContext(overrides = {}) {
  return {
    goal: '',
    selectedModules: [],
    artifacts: {
      role_profile: null,
      jd: null,
      competency_matrix: null,
      interview_questions: null,
      target_companies: null,
      sourcing_keywords: null,
      outreach_strategy: null,
      candidate_scorecard: null,
      evidence_chain: null,
      follow_up_questions: null,
      weekly_summary: null,
      risks: null,
      next_actions: null,
      sourcing_progress: null,
    },
    moduleRuns: [],
    pendingTransfers: [],
    events: [],
    ...overrides,
  }
}

function compactJson(value) {
  if (value === null || value === undefined || value === '') return null
  return value
}

function asStepList(stepsDone) {
  return Array.isArray(stepsDone) ? stepsDone : []
}

function includesAny(value, matchers) {
  const source = String(value || '').toLowerCase()
  return matchers.some((matcher) => source.includes(String(matcher).toLowerCase()))
}

function findObjectValue(output, matchers) {
  if (!output || typeof output !== 'object') return null
  for (const [key, value] of Object.entries(output)) {
    if (includesAny(key, matchers)) return compactJson(value)
  }
  return null
}

export function findStepOutput(stepsDone, matchers) {
  for (const step of asStepList(stepsDone).slice().reverse()) {
    const output = step?.output
    const directValue = findObjectValue(output, matchers)
    if (directValue) return directValue
    const stepText = [step?.label, step?.agent_id, step?.message].filter(Boolean).join(' ')
    if (includesAny(stepText, matchers) && output !== undefined) return output
  }
  return null
}

function firstValue(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== '')
}

function uniqueAppend(list, value) {
  return list.includes(value) ? list : [...list, value]
}

function mergeArtifacts(artifacts, moduleId, result, stepsDone) {
  const next = { ...artifacts }

  if (moduleId === 'A') {
    next.role_profile = firstValue(result?.role_profile, result?.human_report, result, next.role_profile)
    next.jd = firstValue(result?.jd, findStepOutput(stepsDone, ['JD', '职位描述']), next.jd)
    next.competency_matrix = firstValue(
      result?.competency_matrix,
      result?.能力矩阵,
      findStepOutput(stepsDone, ['能力矩阵', 'competency_matrix']),
      next.competency_matrix,
    )
    next.interview_questions = firstValue(
      result?.interview_questions,
      result?.面试问题,
      findStepOutput(stepsDone, ['面试问题', 'interview_questions']),
      next.interview_questions,
    )
  }

  if (moduleId === 'B') {
    next.target_companies = firstValue(
      result?.target_companies,
      result?.动态目标公司,
      findStepOutput(stepsDone, ['目标公司', '动态目标公司']),
      next.target_companies,
    )
    next.sourcing_keywords = firstValue(
      result?.sourcing_keywords,
      result?.搜索关键词,
      findStepOutput(stepsDone, ['关键词', '推荐信源', '搜索关键词']),
      next.sourcing_keywords,
    )
    next.outreach_strategy = firstValue(
      result?.outreach_strategy,
      result?.触达策略,
      findStepOutput(stepsDone, ['触达策略', 'outreach_strategy']),
      next.outreach_strategy,
    )
    next.sourcing_progress = firstValue(result?.sourcing_progress, result, next.sourcing_progress)
  }

  if (moduleId === 'C') {
    next.candidate_scorecard = firstValue(result?.candidate_scorecard, result?.decision_sandbox, result, next.candidate_scorecard)
    next.evidence_chain = firstValue(
      result?.evidence_chain,
      result?.证据记录,
      findStepOutput(stepsDone, ['证据记录', '事实链', 'evidence_chain']),
      next.evidence_chain,
    )
    next.follow_up_questions = firstValue(
      result?.follow_up_questions,
      result?.追问,
      findStepOutput(stepsDone, ['追问', 'follow_up_questions']),
      next.follow_up_questions,
    )
  }

  if (moduleId === 'D') {
    next.weekly_summary = firstValue(result?.weekly_summary, result?.human_report, result, next.weekly_summary)
    next.risks = firstValue(result?.risks, result?.风险, findStepOutput(stepsDone, ['风险', 'risks']), next.risks)
    next.next_actions = firstValue(
      result?.next_actions,
      result?.下周动作,
      findStepOutput(stepsDone, ['下周动作', 'next_actions']),
      next.next_actions,
    )
  }

  return next
}

export function mergeModuleOutput(prev, moduleId, result, stepsDone = [], taskId = null) {
  const module = getModule(moduleId)
  const createdAt = new Date().toISOString()

  return {
    ...prev,
    selectedModules: module ? uniqueAppend(prev.selectedModules || [], moduleId) : prev.selectedModules || [],
    artifacts: mergeArtifacts(prev.artifacts || {}, moduleId, result, stepsDone),
    moduleRuns: [
      ...(prev.moduleRuns || []),
      {
        moduleId,
        moduleTitle: module?.title || moduleId,
        taskId,
        result,
        stepsDone,
        createdAt,
      },
    ],
  }
}

export function getArtifactEntries(context, keys = null) {
  const artifacts = context?.artifacts || {}
  return Object.entries(artifacts)
    .filter(([key, value]) => (!keys || keys.includes(key)) && value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({
      key,
      label: ARTIFACT_LABELS[key] || key,
      value,
    }))
}

export function buildCallReason(fromModule, targetModule, context) {
  const reusable = getArtifactEntries(context, targetModule.consumes).map((item) => item.label)
  if (!reusable.length) {
    return `${fromModule.title} 已完成，但 ${targetModule.title} 仍缺少关键输入，需要人工补充后继续。`
  }
  return `${fromModule.title} 已完成，${targetModule.title} 可复用 ${reusable.join('、')}。`
}

export function getRecommendedModuleCalls(context, completedModuleId) {
  const module = getModule(completedModuleId)
  if (!module) return []

  return module.next
    .map((targetModuleId) => {
      const target = getModule(targetModuleId)
      if (!target) return null
      const missingInputs = target.consumes.filter((key) => key !== 'goal' && !context?.artifacts?.[key])
      const reusableInputs = target.consumes.filter((key) => context?.artifacts?.[key])

      return {
        from: completedModuleId,
        to: targetModuleId,
        title: `${module.title} → ${target.title}`,
        reason: buildCallReason(module, target, context),
        missingInputs,
        reusableInputs,
        riskLevel: missingInputs.length ? 'medium' : 'low',
      }
    })
    .filter(Boolean)
}

export function createModuleCall({ from, to, context }) {
  const source = getModule(from)
  const target = getModule(to)
  if (!source || !target) return null
  const [recommendation] = getRecommendedModuleCalls(context, from).filter((call) => call.to === to)
  const missingInputs = target.consumes.filter((key) => key !== 'goal' && !context?.artifacts?.[key])
  const reusableInputs = target.consumes.filter((key) => context?.artifacts?.[key])

  return {
    id: `${from}-${to}-${Date.now()}`,
    from,
    to,
    title: `${source.title} → ${target.title}`,
    reason: recommendation?.reason || buildCallReason(source, target, context),
    missingInputs,
    reusableInputs,
    riskLevel: missingInputs.length ? 'medium' : 'low',
    createdAt: new Date().toISOString(),
  }
}

function formatPayload(value) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function buildModuleInput({ from, to, userInput = '', context, edits = null }) {
  const source = getModule(from)
  const target = getModule(to)
  if (!target) return userInput || context?.goal || ''

  const consumedArtifacts = Object.fromEntries(
    getArtifactEntries(context, target.consumes).map((item) => [item.key, item.value]),
  )

  return [
    `用户目标：${context?.goal || userInput}`,
    `当前要执行的能力：${target.title}`,
    `上游模块：${source?.title || '用户直接触发'}`,
    `可复用上下文：${JSON.stringify(consumedArtifacts, null, 2)}`,
    edits ? `人工补充/修改：${formatPayload(edits)}` : '',
  ]
    .filter(Boolean)
    .join('\n\n')
}

export function buildDirectModuleInput({ moduleId, rawInput, context }) {
  const target = getModule(moduleId)
  const reusable = getArtifactEntries(context, target?.consumes || [])
  if (!target || !reusable.length) return rawInput.trim()

  return [
    `用户目标：${context?.goal || rawInput}`,
    `当前要执行的能力：${target.title}`,
    `用户原始输入：${rawInput.trim()}`,
    `可复用上下文：${JSON.stringify(Object.fromEntries(reusable.map((item) => [item.key, item.value])), null, 2)}`,
  ].join('\n\n')
}
