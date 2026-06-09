import { useEffect, useState } from 'react'

function formatCall(call) {
  return `${call.method} ${call.path}${call.optional ? ' · 可选' : ''}`
}

function formatInput(input) {
  const suffix = input.required ? '必填' : '可选'
  return `${input.label || input.name} · ${suffix}`
}

function CapabilityCard({ capability, onExecute, busy }) {
  return (
    <article className={`capability-card risk-${capability.riskLevel}`}>
      <div className="capability-card-head">
        <div>
          <span>{capability.workspace}</span>
          <strong>{capability.title}</strong>
        </div>
        <span className="capability-risk">{capability.riskLevel}</span>
      </div>
      <p>{capability.description}</p>
      <div className="capability-contract">
        <div>
          <span>会调用</span>
          {capability.apiCalls.map((call) => (
            <code key={`${capability.id}-${call.path}-${call.client}`}>{formatCall(call)}</code>
          ))}
        </div>
        <div>
          <span>需要输入</span>
          {(capability.inputs.length ? capability.inputs : [{ name: 'none', label: '无需额外输入' }]).map((input) => (
            <code key={`${capability.id}-${input.name}`}>{formatInput(input)}</code>
          ))}
        </div>
        <div>
          <span>产出 artifact</span>
          {(capability.artifacts.length ? capability.artifacts : ['无']).map((artifact) => (
            <code key={`${capability.id}-${artifact}`}>{artifact}</code>
          ))}
        </div>
      </div>
      <div className="capability-card-foot">
        <span>{capability.writeScope === 'none' ? '不写入' : `写入：${capability.writeScope}`}</span>
        <span>{capability.requiresConfirmation ? '需要确认' : '可直接读取'}</span>
        <button className="btn btn-run" type="button" onClick={() => onExecute(capability)} disabled={busy}>
          执行
        </button>
      </div>
    </article>
  )
}

function initialFormValues(capability, prompt) {
  return Object.fromEntries(
    capability.inputs.map((input) => {
      if (input.name === 'query' || input.name === 'input' || input.name === 'itemsText') {
        return [input.name, prompt || input.defaultValue || '']
      }
      if (input.name === 'claim') return [input.name, prompt || input.defaultValue || '']
      return [input.name, input.defaultValue ?? (input.type === 'boolean' ? false : '')]
    }),
  )
}

function CapabilityInputForm({ capability, prompt, values, setValues }) {
  useEffect(() => {
    setValues(initialFormValues(capability, prompt))
  }, [capability, prompt, setValues])

  if (!capability.inputs.length) return <div className="schema-empty">无需额外输入。</div>

  return (
    <div className="schema-form" aria-label="能力输入表单">
      {capability.inputs.map((input) => {
        const value = values[input.name]
        if (input.type === 'boolean') {
          return (
            <label className="schema-field schema-check" key={input.name}>
              <input
                checked={Boolean(value)}
                type="checkbox"
                onChange={(event) => setValues((prev) => ({ ...prev, [input.name]: event.target.checked }))}
              />
              <span>{input.label || input.name}</span>
            </label>
          )
        }
        if (input.type === 'select') {
          return (
            <label className="schema-field" key={input.name}>
              <span>{input.label || input.name}</span>
              <select
                value={value ?? ''}
                onChange={(event) => setValues((prev) => ({ ...prev, [input.name]: event.target.value }))}
              >
                {(input.options || []).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
          )
        }
        const Control = input.type === 'textarea' ? 'textarea' : 'input'
        return (
          <label className="schema-field" key={input.name}>
            <span>{input.label || input.name}</span>
            <Control
              value={value ?? ''}
              type={input.type === 'number' ? 'number' : 'text'}
              rows={input.type === 'textarea' ? 4 : undefined}
              onChange={(event) => {
                const nextValue = input.type === 'number' ? Number(event.target.value) : event.target.value
                setValues((prev) => ({ ...prev, [input.name]: nextValue }))
              }}
            />
          </label>
        )
      })}
    </div>
  )
}

export default function ChatShell({
  activeRuns,
  busy,
  messages,
  onCancelConfirmation,
  onConfirmCapability,
  onRequestCapability,
  onSubmitPrompt,
  pendingConfirmation,
  prompt,
  setPrompt,
  suggestedCapabilities,
}) {
  const [confirmationValues, setConfirmationValues] = useState({})

  function executeCapability(capability) {
    onRequestCapability(capability)
  }

  function handleSubmit(event) {
    event.preventDefault()
    onSubmitPrompt(prompt)
  }

  return (
    <section className="chat-shell" aria-label="聊天主入口">
      <div className="chat-scroll">
        {messages.map((message) => (
          <article className={`chat-message message-${message.role}`} key={message.id}>
            <span>{message.role === 'user' ? '你' : 'Agent'}</span>
            <p>{message.text}</p>
          </article>
        ))}

        {suggestedCapabilities.length > 0 && (
          <section className="suggestion-block" aria-label="推荐能力">
            <div className="suggestion-head">
              <span className="section-label">推荐能力</span>
              <strong>{suggestedCapabilities.length} 个待确认能力</strong>
            </div>
            <div className="capability-card-list">
              {suggestedCapabilities.map((capability) => (
                <CapabilityCard
                  busy={busy}
                  capability={capability}
                  key={capability.id}
                  onExecute={executeCapability}
                />
              ))}
            </div>
          </section>
        )}

        {pendingConfirmation && (
          <section className="confirmation-panel" aria-label="能力执行确认">
            <div>
              <span className="section-label">Human Confirmation</span>
              <strong>{pendingConfirmation.capability.title}</strong>
              <p>{pendingConfirmation.capability.description}</p>
            </div>
            <div className="confirmation-facts">
              <span>风险：{pendingConfirmation.capability.riskLevel}</span>
              <span>写入：{pendingConfirmation.capability.writeScope}</span>
              <span>输入：{pendingConfirmation.prompt || '无'}</span>
            </div>
            <CapabilityInputForm
              capability={pendingConfirmation.capability}
              prompt={pendingConfirmation.prompt}
              setValues={setConfirmationValues}
              values={confirmationValues}
            />
            <div className="confirmation-actions">
              <button className="btn btn-ghost" type="button" onClick={onCancelConfirmation} disabled={busy}>
                取消
              </button>
              <button className="btn btn-run" type="button" onClick={() => onConfirmCapability(confirmationValues)} disabled={busy}>
                确认执行
              </button>
            </div>
          </section>
        )}

        {activeRuns.length > 0 && (
          <section className="run-strip" aria-label="能力执行日志">
            {activeRuns.slice(0, 5).map((run) => (
              <div className={`run-chip run-${run.status}`} key={run.id}>
                <span>{run.status}</span>
                <strong>{run.title}</strong>
              </div>
            ))}
          </section>
        )}
      </div>

      <form className="chat-composer" onSubmit={handleSubmit}>
        <textarea
          aria-label="统一输入框"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="输入招聘目标、搜索问题、候选人匹配或 RSI 评估需求"
          rows={3}
        />
        <div className="chat-composer-actions">
          <button className="btn btn-run" type="submit" disabled={busy || !prompt.trim()}>
            推荐能力
          </button>
        </div>
      </form>
    </section>
  )
}
