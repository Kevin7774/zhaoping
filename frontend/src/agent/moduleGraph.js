export const MODULE_GRAPH = {
  A: {
    id: 'A',
    title: '岗位画像',
    description: '生成岗位画像、JD、能力矩阵、面试题',
    provides: ['role_profile', 'jd', 'competency_matrix', 'interview_questions'],
    consumes: ['goal', 'team_constraint'],
    canCall: ['B', 'C'],
    next: ['B'],
  },
  B: {
    id: 'B',
    title: '人才地图',
    description: '构建目标公司、搜索关键词、触达策略',
    provides: ['target_companies', 'sourcing_keywords', 'outreach_strategy'],
    consumes: ['role_profile', 'competency_matrix'],
    canCall: ['A', 'C'],
    next: ['C'],
  },
  C: {
    id: 'C',
    title: '候选评估',
    description: '输出评分卡、证据链、追问清单',
    provides: ['candidate_scorecard', 'evidence_chain', 'follow_up_questions'],
    consumes: ['role_profile', 'target_companies', 'competency_matrix'],
    canCall: ['A', 'B', 'D'],
    next: ['D'],
  },
  D: {
    id: 'D',
    title: '招聘周报',
    description: '汇总进展、风险、下周动作',
    provides: ['weekly_summary', 'risks', 'next_actions'],
    consumes: ['role_profile', 'sourcing_progress', 'candidate_scorecard'],
    canCall: ['A', 'B', 'C'],
    next: [],
  },
}

export const MODULE_SEQUENCE = ['A', 'B', 'C', 'D']

export function getModule(moduleId) {
  return MODULE_GRAPH[moduleId] || null
}
