import { useMemo, useState } from 'react'
import {
  createWorkflowSession,
  retryWorkflowNode,
  runWorkflowNode,
  skipWorkflowNode,
} from '../api.js'
import JsonView from './JsonView.jsx'

const STATUS_LABEL = {
  idle: '待运行',
  active: '执行中',
  awaiting: '待确认',
  done: '已完成',
  skipped: '已跳过',
  error: '异常',
}

function labelList(items) {
  if (!items?.length) return '无'
  return items.join(' / ')
}

function artifactSummary(value) {
  if (value === null || value === undefined || value === '') return '空'
  if (Array.isArray(value)) return `${value.length} 项`
  if (typeof value === 'object') return `${Object.keys(value).length} 字段`
  return String(value).length > 64 ? `${String(value).slice(0, 64)}...` : String(value)
}

export default function AtomicWorkflowPanel({
  apertureWeight,
  disabled,
  input,
  scenario,
  scenarioId,
  teamConstraint,
}) {
  const [session, setSession] = useState(null)
  const [busyNodeId, setBusyNodeId] = useState(null)
  const [error, setError] = useState(null)
  const [editDrafts, setEditDrafts] = useState({})
  const workflow = session?.workflow || null
  const nodes = useMemo(() => workflow?.nodes || [], [workflow?.nodes])
  const artifacts = workflow?.artifacts || {}
  const completeCount = useMemo(
    () => nodes.filter((node) => node.status === 'done' || node.status === 'skipped').length,
    [nodes],
  )
  const currentScenarioId = scenarioId || scenario?.id
  const busy = Boolean(busyNodeId)
  const canCreate = Boolean(currentScenarioId && input?.trim() && !disabled && !busy)

  async function createSession() {
    if (!canCreate) return null
    setError(null)
    setBusyNodeId('session')
    try {
      const snapshot = await createWorkflowSession(currentScenarioId, input.trim(), {
        teamConstraint,
        apertureWeight,
        frontendState: { source: 'atomic_workflow_panel' },
      })
      setSession(snapshot)
      return snapshot
    } catch (e) {
      setError(e.message)
      return null
    } finally {
      setBusyNodeId(null)
    }
  }

  async function ensureSession() {
    if (session?.task_id) return session
    return createSession()
  }

  async function executeNode(node, action, payload = {}) {
    const activeSession = await ensureSession()
    if (!activeSession?.task_id || !node?.node_id) return
    setError(null)
    setBusyNodeId(node.node_id)
    try {
      let snapshot
      if (action === 'skip') {
        snapshot = await skipWorkflowNode(activeSession.task_id, node.node_id)
      } else if (action === 'retry') {
        snapshot = await retryWorkflowNode(activeSession.task_id, node.node_id, payload)
      } else {
        snapshot = await runWorkflowNode(activeSession.task_id, node.node_id, payload)
      }
      setSession(snapshot)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusyNodeId(null)
    }
  }

  function submitHumanNode(node, decision) {
    const edits = editDrafts[node.node_id]?.trim() || null
    executeNode(node, node.status === 'done' ? 'retry' : 'run', { decision, edits })
  }

  return (
    <section className="atomic-panel" aria-label="原子级控制">
      <div className="atomic-head">
        <div>
          <div className="section-label">Atomic Runtime</div>
          <h2>原子级控制</h2>
          <p>{scenario?.name_zh || currentScenarioId || '未选择'} · {session?.task_id || '未创建会话'}</p>
        </div>
        <button className="btn btn-run" type="button" onClick={createSession} disabled={!canCreate}>
          {busyNodeId === 'session' ? '创建中' : session ? '重建会话' : '创建原子会话'}
        </button>
      </div>

      <div className="atomic-meter">
        <span>{completeCount}/{nodes.length || scenario?.steps?.length || 0} nodes</span>
        <span>{Object.keys(artifacts).length} artifacts</span>
        <span>{teamConstraint || '真机泛化'} · {Math.round(Number(apertureWeight || 0.7) * 100)}%</span>
      </div>

      {error && <div className="banner banner-error atomic-error">{error}</div>}
      {!session && <div className="atomic-empty">输入招聘目标后，可创建原子会话，再逐节点单步运行。</div>}

      {workflow && (
        <>
          <div className="atomic-node-list">
            {nodes.map((node) => (
              <article className={`atomic-node node-${node.status}`} key={node.node_id}>
                <div className="atomic-node-main">
                  <span className="atomic-node-id">{node.node_id}</span>
                  <div>
                    <strong>{node.label}</strong>
                    <p>{node.message}</p>
                  </div>
                  <span className={`atomic-status status-${node.status}`}>{STATUS_LABEL[node.status] || node.status}</span>
                </div>
                <div className="atomic-node-contract">
                  <span>输入：{labelList(node.inputs)}</span>
                  <span>输出：{labelList(node.outputs)}</span>
                  <span>运行：{node.run_count || 0}</span>
                </div>
                {node.error && <div className="atomic-node-error">{node.error}</div>}
                {node.output && (
                  <details className="atomic-output">
                    <summary>查看节点输出</summary>
                    <JsonView value={node.output} />
                  </details>
                )}
                {node.requires_human && node.status === 'awaiting' && (
                  <div className="atomic-human">
                    <textarea
                      value={editDrafts[node.node_id] || ''}
                      onChange={(event) => setEditDrafts((drafts) => ({ ...drafts, [node.node_id]: event.target.value }))}
                      placeholder="可选：人工修改意见"
                      rows={2}
                    />
                    <button className="btn btn-approve" type="button" disabled={busy} onClick={() => submitHumanNode(node, 'approve')}>
                      通过
                    </button>
                    <button className="btn btn-edit" type="button" disabled={busy} onClick={() => submitHumanNode(node, 'edit')}>
                      按修改继续
                    </button>
                    <button className="btn btn-reject" type="button" disabled={busy} onClick={() => submitHumanNode(node, 'reject')}>
                      拒绝
                    </button>
                  </div>
                )}
                <div className="atomic-actions">
                  <button className="btn btn-run" type="button" disabled={busy || disabled} onClick={() => executeNode(node, 'run')}>
                    {busyNodeId === node.node_id ? '运行中' : '单步运行'}
                  </button>
                  <button className="btn btn-ghost" type="button" disabled={busy || disabled} onClick={() => executeNode(node, 'skip')}>
                    跳过节点
                  </button>
                  <button className="btn btn-edit" type="button" disabled={busy || disabled} onClick={() => executeNode(node, 'retry')}>
                    重跑节点
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className="atomic-artifacts" aria-label="原子产物">
            {Object.entries(artifacts).map(([key, value]) => (
              <div className="atomic-artifact" key={key}>
                <span>{key}</span>
                <strong>{artifactSummary(value)}</strong>
              </div>
            ))}
            {!Object.keys(artifacts).length && <div className="atomic-empty">节点输出会沉淀为 artifact。</div>}
          </div>
        </>
      )}
    </section>
  )
}
