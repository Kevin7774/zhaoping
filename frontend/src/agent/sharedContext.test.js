import assert from 'node:assert/strict'
import { test } from 'node:test'

import { MODULE_GRAPH } from './moduleGraph.js'
import {
  buildModuleInput,
  createInitialAgentContext,
  getRecommendedModuleCalls,
  mergeModuleOutput,
} from './sharedContext.js'

test('module graph models the recruiting workspace chain', () => {
  assert.deepEqual(MODULE_GRAPH.A.next, ['B'])
  assert.deepEqual(MODULE_GRAPH.B.consumes, ['role_profile', 'competency_matrix'])
  assert.equal(MODULE_GRAPH.C.title, '候选评估')
  assert.ok(MODULE_GRAPH.D.consumes.includes('candidate_scorecard'))
})

test('mergeModuleOutput stores role profile artifacts without mutating previous context', () => {
  const previous = createInitialAgentContext({ goal: '招聘机器人产品负责人' })
  const next = mergeModuleOutput(
    previous,
    'A',
    { role_profile: { title: '机器人产品负责人' } },
    [{ label: '能力矩阵生成', output: { 能力矩阵: ['VLA', '真机泛化'] } }],
    'task-a-1',
  )

  assert.equal(previous.artifacts.role_profile, null)
  assert.deepEqual(next.artifacts.role_profile, { title: '机器人产品负责人' })
  assert.deepEqual(next.artifacts.competency_matrix, ['VLA', '真机泛化'])
  assert.equal(next.moduleRuns.length, 1)
  assert.equal(next.moduleRuns[0].taskId, 'task-a-1')
})

test('completed role profile recommends a low-risk talent map call', () => {
  const context = createInitialAgentContext({ goal: '招聘机器人产品负责人' })
  const next = mergeModuleOutput(
    context,
    'A',
    {
      role_profile: { title: '机器人产品负责人' },
      competency_matrix: ['VLA', '真机泛化'],
    },
    [],
    'task-a-2',
  )

  const [call] = getRecommendedModuleCalls(next, 'A')

  assert.equal(call.from, 'A')
  assert.equal(call.to, 'B')
  assert.equal(call.riskLevel, 'low')
  assert.deepEqual(call.missingInputs, [])
  assert.deepEqual(call.reusableInputs, ['role_profile', 'competency_matrix'])
})

test('buildModuleInput passes only target-consumed artifacts plus human edits', () => {
  const context = createInitialAgentContext({ goal: '招聘机器人产品负责人' })
  const withArtifacts = {
    ...context,
    artifacts: {
      ...context.artifacts,
      role_profile: { title: '机器人产品负责人' },
      competency_matrix: ['VLA'],
      weekly_summary: { stale: true },
    },
  }

  const input = buildModuleInput({
    from: 'A',
    to: 'B',
    context: withArtifacts,
    edits: '优先找有量产机器人经验的人',
  })

  assert.match(input, /当前要执行的能力：人才地图/)
  assert.match(input, /上游模块：岗位画像/)
  assert.match(input, /role_profile/)
  assert.match(input, /competency_matrix/)
  assert.doesNotMatch(input, /weekly_summary/)
  assert.match(input, /优先找有量产机器人经验的人/)
})
