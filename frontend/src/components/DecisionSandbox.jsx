import { useMemo, useState } from 'react'
import { sendProbeFeedback } from '../api.js'
import JsonView from './JsonView.jsx'

function focusTerms(text) {
  const normalized = (text || '').toLowerCase()
  const groups = {
    真机泛化: ['真机', '实机', '部署', 'sim-to-real', '泛化', '长尾', '家庭'],
    动作延迟: ['延迟', '时延', '实时', '控制', 'jitter', '同步'],
    数据闭环: ['数据', '遥操作', '采集', '清洗', '时间戳', '多摄像头'],
    灵巧操作: ['抓取', '操作', '灵巧手', '触觉', '柔性'],
    系统联调: ['软硬件', '系统', 'ros', '总线', '联调', '故障'],
  }
  const matched = Object.entries(groups).find(([label, terms]) =>
    normalized.includes(label.toLowerCase()) || terms.some((term) => normalized.includes(term.toLowerCase())),
  )
  if (matched) return matched[1]
  return normalized.split(/[\s,，/]+/).filter(Boolean).slice(0, 6)
}

function focusScore(item, terms, base = 0) {
  const haystack = JSON.stringify(item || {}).toLowerCase()
  const hits = terms.filter((term) => haystack.includes(term.toLowerCase())).length
  return base + hits * 18
}

function stateLabel(value) {
  if (value === null || value === undefined) return '缺证据'
  if (value >= 76) return '涌现'
  if (value <= 42) return '收缩'
  return '验证'
}

function sortedByFocus(items, terms, weight) {
  return [...(items || [])].sort((a, b) => {
    const aScore = focusScore(a, terms, Number(a.transfer_score || a.energy || 0) * weight)
    const bScore = focusScore(b, terms, Number(b.transfer_score || b.energy || 0) * weight)
    return bScore - aScore
  })
}

export default function DecisionSandbox({ task, teamConstraint, apertureWeight }) {
  const sandbox = task?.result?.decision_sandbox || {}
  const aperture = sandbox.aperture_anchor || sandbox.aperture || {}
  const narrative = sandbox.narrative_stream || {}
  const [copiedId, setCopiedId] = useState(null)
  const [feedback, setFeedback] = useState(() => {
    const items = sandbox.feedback_loop?.feedback || []
    return Object.fromEntries(items.map((item) => [item.probe_id, item.answered ? 'answered' : 'missed']))
  })
  const [feedbackError, setFeedbackError] = useState(null)
  const terms = useMemo(() => aperture.focus_terms || focusTerms(aperture.team_constraint || teamConstraint), [aperture.focus_terms, aperture.team_constraint, teamConstraint])
  const weight = Math.max(0.1, Math.min(Number(apertureWeight || 0.7), 1))
  const rawSpectrum = useMemo(() => sandbox.capability_spectrum || sandbox.spectrum || [], [sandbox.capability_spectrum, sandbox.spectrum])
  const rawProjections = useMemo(() => sandbox.cognitive_projection || sandbox.projection || [], [sandbox.cognitive_projection, sandbox.projection])
  const spectrum = useMemo(() => sortedByFocus(rawSpectrum, terms, weight), [rawSpectrum, terms, weight])
  const projections = useMemo(() => sortedByFocus(rawProjections, terms, weight), [rawProjections, terms, weight])
  const dynamicCore = narrative.core_incremental_value || sandbox.core_incremental_value || '数据不足，无法推演。'
  const apertureDrift = teamConstraint && aperture.team_constraint && teamConstraint !== aperture.team_constraint

  async function copyProbe(probe) {
    try {
      await navigator.clipboard.writeText(probe.question)
      setCopiedId(probe.id)
      window.setTimeout(() => setCopiedId(null), 1300)
    } catch {
      setCopiedId('error')
      window.setTimeout(() => setCopiedId(null), 1300)
    }
  }

  async function recordFeedback(probe, answered) {
    setFeedbackError(null)
    setFeedback((prev) => ({ ...prev, [probe.id]: answered ? 'answered' : 'missed' }))
    try {
      await sendProbeFeedback(task.task_id, probe.id, answered, `Aperture=${teamConstraint}`)
    } catch (e) {
      setFeedbackError(e.message)
    }
  }

  return (
    <div className="decision-sandbox">
      <section className="sandbox-matrix" aria-label="候选评估矩阵">
        {(sandbox.agent_matrix || []).map((node) => (
          <article className="matrix-node" key={node.id}>
            <span>{node.label}</span>
            <strong>{node.output}</strong>
            <em>{node.status}</em>
          </article>
        ))}
      </section>

      {apertureDrift && (
        <div className="sandbox-warning">
          当前筛选条件是「{teamConstraint}」，本次评估锚点是「{aperture.team_constraint}」。需重新执行任务以刷新评估结果。
        </div>
      )}

      <div className="sandbox-layout">
        <aside className="spectrum-panel">
          <div className="sandbox-panel-head">
            <span>The Spectrum</span>
            <strong>工程能力动能频谱</strong>
          </div>
          <div className="spectrum-list">
            {spectrum.map((item) => (
              <div className={`spectrum-row temp-${item.temperature}`} key={item.id}>
                <div className="spectrum-row-head">
                  <span>{item.label}</span>
                  <strong>{stateLabel(item.energy)}</strong>
                </div>
                <div className="spectrum-track" aria-label={`${item.label} ${item.signal}`}>
                  <div className="spectrum-fill" style={{ width: item.energy === null || item.energy === undefined ? '0%' : `${Math.max(8, item.energy)}%` }} />
                </div>
                <p>{item.blocked_reason || item.boundary}</p>
              </div>
            ))}
          </div>
        </aside>

        <section className="narrative-workbench">
          <div className="sandbox-panel-head">
            <span>The Narrative Workbench</span>
            <strong>增量价值叙事流</strong>
          </div>

          <article className="core-value">
            <span>{narrative.status || 'narrative_stream'}</span>
            <h2>{dynamicCore}</h2>
            <p>{sandbox.emergent_strength}</p>
          </article>

          {narrative.causal_chain?.length > 0 && (
            <section className="causal-chain">
              {narrative.causal_chain.map((item) => (
                <article key={item.step}>
                  <span>{item.step}</span>
                  <strong>{item.state}</strong>
                </article>
              ))}
            </section>
          )}

          <section className="projection-section">
            <h3>能力平移推演</h3>
            <div className="projection-list">
              {projections.length === 0 && (
                <div className="sandbox-empty">数据不足，Task D 未生成能力平移推演。</div>
              )}
              {projections.map((item, index) => (
                <article className="projection-card" key={`${item.from_fact}-${index}`}>
                  <div>
                    <span>他做过的事实</span>
                    <strong>{item.from_fact}</strong>
                  </div>
                  <div>
                    <span>预测能迁移到</span>
                    <strong>{item.to_team_need}</strong>
                  </div>
                  <p>{item.validation_needed}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="hidden-limits">
            <h3>The Hidden Limits</h3>
            <ul>
              {(sandbox.hidden_limits || []).map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>

          <details className="fact-chain">
            <summary>工程事实链</summary>
            <div className="fact-list">
              {(sandbox.fact_chain || []).map((fact) => (
                <article key={fact.id}>
                  <span>{fact.label}</span>
                  <strong>{fact.value}</strong>
                  <p>{fact.verification_status} · {fact.evidence}</p>
                </article>
              ))}
            </div>
          </details>
        </section>

        <aside className="probe-toolkit">
          <div className="sandbox-panel-head">
            <span>The Probing Toolkit</span>
            <strong>苏格拉底追问武器库</strong>
          </div>
          {(sandbox.probing_toolkit || []).map((probe) => (
            <article className="probe-card" key={probe.id}>
              <div className="probe-id">{probe.id}</div>
              <p>{probe.question}</p>
              <span>{probe.success_signal}</span>
              <div className="probe-actions">
                <button type="button" className="btn btn-ghost" onClick={() => copyProbe(probe)}>
                  {copiedId === probe.id ? '已复制' : '复制'}
                </button>
                <button
                  type="button"
                  className={`btn btn-approve ${feedback[probe.id] === 'answered' ? 'probe-selected' : ''}`}
                  onClick={() => recordFeedback(probe, true)}
                >
                  答出
                </button>
                <button
                  type="button"
                  className={`btn btn-reject ${feedback[probe.id] === 'missed' ? 'probe-selected' : ''}`}
                  onClick={() => recordFeedback(probe, false)}
                >
                  未答出
                </button>
              </div>
            </article>
          ))}
          {feedbackError && <div className="probe-error">反馈回写失败：{feedbackError}</div>}
          <div className="feedback-loop">
            <strong>反馈闭环</strong>
            <p>{sandbox.feedback_loop?.model_update_policy}</p>
          </div>
        </aside>
      </div>

      <details className="hr-raw">
        <summary>查看原始结构化数据</summary>
        <JsonView value={task.result} />
      </details>
    </div>
  )
}
