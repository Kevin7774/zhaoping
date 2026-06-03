import JsonView from './JsonView.jsx'

// Renders the agent sequence for the active scenario purely from backend meta.
// Highlights live state from the polled task; never hardcodes the flow.

function stepStatus(index, task) {
  if (!task) return 'idle'
  const { status, current_step } = task
  if (status === 'done') return 'done'
  if (index < current_step) return 'done'
  if (index === current_step) {
    if (status === 'awaiting_human') return 'awaiting'
    if (status === 'error') return 'error'
    return 'active'
  }
  return 'pending'
}

const STATUS_LABEL = {
  idle: '待运行',
  pending: '等待中…',
  active: '执行中…',
  awaiting: '等待人工',
  done: '完成',
  error: '异常',
}

export default function AgentFlow({ steps, agents, task }) {
  const doneOutputs = task?.steps_done || []

  return (
    <div className="agent-flow">
      {steps.map((step, index) => {
        const agent = agents[step.agent_id] || {}
        const state = stepStatus(index, task)
        const output = doneOutputs[index]?.output
        return (
          <div className={`flow-node state-${state} kind-${step.kind}`} key={index}>
            <div className="flow-rail">
              <div className="flow-dot">{agent.icon || '•'}</div>
              {index < steps.length - 1 && <div className="flow-line" />}
            </div>
            <div className="flow-card">
              <div className="flow-head">
                <span className="flow-agent">{agent.name_zh || step.agent_id}</span>
                <span className={`flow-badge badge-${state}`}>{STATUS_LABEL[state]}</span>
              </div>
              <div className="flow-label">{step.label} · {step.message}</div>
              {state === 'active' && (
                <div className="flow-thinking">
                  <span className="dot" /><span className="dot" /><span className="dot" />
                  <em>{agent.persona}</em>
                </div>
              )}
              {state === 'pending' && <div className="flow-shadow">{agent.output_format} · 思考中…</div>}
              {output !== undefined && output !== null && (
                <div className="flow-output">
                  <JsonView value={output} />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
