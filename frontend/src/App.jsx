import { useEffect, useRef, useState } from 'react'
import { confirmTask, fetchMeta, fetchTask, runScenario } from './api.js'
import AgentFlow from './components/AgentFlow.jsx'
import LogStream from './components/LogStream.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import HumanGate from './components/HumanGate.jsx'

const STATUS_TEXT = {
  processing: '执行中',
  awaiting_human: '等待人工确认',
  done: '已完成',
  error: '已终止',
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState(null)
  const [activeScenario, setActiveScenario] = useState('A')
  const [input, setInput] = useState('')
  const [task, setTask] = useState(null)
  const [busy, setBusy] = useState(false)
  const [runError, setRunError] = useState(null)
  const pollRef = useRef(null)

  // Load the orchestration protocol once; everything renders from this.
  useEffect(() => {
    fetchMeta()
      .then((data) => {
        setMeta(data)
        if (data.scenarios?.length) setActiveScenario(data.scenarios[0].id)
      })
      .catch((e) => setMetaError(e.message))
  }, [])

  // Poll task state while the backend is live (processing, or paused awaiting a
  // human — so we reliably catch the transition right after the user confirms).
  useEffect(() => {
    if (!task?.task_id) return
    if (task.status !== 'processing' && task.status !== 'awaiting_human') return
    pollRef.current = setInterval(async () => {
      try {
        const snap = await fetchTask(task.task_id)
        setTask(snap)
      } catch (e) {
        setRunError(e.message)
        clearInterval(pollRef.current)
      }
    }, 600)
    return () => clearInterval(pollRef.current)
  }, [task?.task_id, task?.status])

  const scenarios = meta?.scenarios || []
  const current = scenarios.find((s) => s.id === activeScenario)
  const agents = meta?.agents || {}

  const running = task && (task.status === 'processing' || task.status === 'awaiting_human')

  async function handleRun() {
    if (!input.trim() || running) return
    setRunError(null)
    setBusy(true)
    try {
      const { task_id } = await runScenario(activeScenario, input.trim())
      const snap = await fetchTask(task_id)
      setTask(snap)
    } catch (e) {
      setRunError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirm(decision, edits) {
    if (!task?.task_id) return
    setBusy(true)
    try {
      const snap = await confirmTask(task.task_id, decision, edits)
      // The runner thread may not have transitioned yet; locally clear the gate
      // (unless rejected) so polling smoothly carries the task forward.
      if (snap.status === 'awaiting_human' && decision !== 'reject') {
        setTask({ ...snap, status: 'processing', awaiting: null })
      } else {
        setTask(snap)
      }
    } catch (e) {
      setRunError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function useExample() {
    if (current?.example) setInput(current.example)
  }

  function selectScenario(id) {
    if (running) return
    setActiveScenario(id)
    setTask(null)
    setRunError(null)
  }

  const progress = task ? Math.min(100, Math.round(((task.current_step + 1) / task.total_steps) * 100)) : 0

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-logo">🤖</span>
          <div>
            <div className="brand-title">机器人招聘 Agent 运行时 Dashboard</div>
            <div className="brand-sub">编排在后端 · 状态实时推送 · Human-in-the-loop 可干预</div>
          </div>
        </div>
        {task && (
          <div className={`run-status status-${task.status}`}>
            {STATUS_TEXT[task.status] || task.status}
            <span className="run-step">
              {task.current_step + 1}/{task.total_steps}
            </span>
          </div>
        )}
      </header>

      {metaError && <div className="banner banner-error">无法加载后端协议：{metaError}（请先启动 FastAPI: uvicorn app.api.main:app --port 8000）</div>}

      <div className="scenario-tabs">
        {scenarios.map((s) => (
          <button
            key={s.id}
            className={`tab ${s.id === activeScenario ? 'tab-active' : ''}`}
            onClick={() => selectScenario(s.id)}
            disabled={running}
          >
            {s.name_zh}
          </button>
        ))}
      </div>

      <div className="composer">
        <textarea
          className="composer-input"
          placeholder={current?.input_hint || '输入招聘需求…'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={3}
          disabled={running}
        />
        <div className="composer-actions">
          <button className="btn btn-ghost" onClick={useExample} disabled={running || !current?.example}>
            填入示例
          </button>
          <button className="btn btn-run" onClick={handleRun} disabled={busy || running || !input.trim()}>
            {running ? '运行中…' : '运行 Agent'}
          </button>
        </div>
      </div>

      {runError && <div className="banner banner-error">{runError}</div>}

      {task && (
        <div className="progress-track">
          <div className={`progress-fill status-${task.status}`} style={{ width: `${progress}%` }} />
        </div>
      )}

      <main className="workspace">
        <section className="col col-flow">
          <div className="col-title">Agent 流转</div>
          {current ? (
            <AgentFlow steps={current.steps} agents={agents} task={task} />
          ) : (
            <div className="result-empty">加载场景中…</div>
          )}
        </section>

        <section className="col col-side">
          {task?.status === 'awaiting_human' && task.awaiting && (
            <HumanGate awaiting={task.awaiting} busy={busy} onConfirm={handleConfirm} />
          )}
          <LogStream logs={task?.logs} />
          <div className="col-title">最终报告</div>
          <ResultPanel task={task} />
        </section>
      </main>
    </div>
  )
}
