import { useState } from 'react'
import JsonView from './JsonView.jsx'

// Human-in-the-loop panel. Appears when the task is paused (awaiting_human).
// Lets the expert approve, edit, or reject, then drives the agent to continue.

export default function HumanGate({ awaiting, busy, onConfirm }) {
  const [edits, setEdits] = useState('')

  if (!awaiting) return null

  return (
    <div className="human-gate">
      <div className="gate-tag">🧑‍⚖️ Human-in-the-loop · 流程已暂停</div>
      <div className="gate-prompt">{awaiting.prompt}</div>

      <div className="gate-draft">
        <div className="gate-draft-title">待确认草稿</div>
        <JsonView value={awaiting.draft} />
      </div>

      <textarea
        className="gate-input"
        placeholder="（可选）填写修改意见 / 人工补充，点“按修改继续”后会并入结果"
        value={edits}
        onChange={(e) => setEdits(e.target.value)}
        rows={3}
      />

      <div className="gate-actions">
        <button className="btn btn-approve" disabled={busy} onClick={() => onConfirm('approve', null)}>
          通过并继续
        </button>
        <button
          className="btn btn-edit"
          disabled={busy || !edits.trim()}
          onClick={() => onConfirm('edit', edits.trim())}
        >
          按修改继续
        </button>
        <button className="btn btn-reject" disabled={busy} onClick={() => onConfirm('reject', null)}>
          拒绝并终止
        </button>
      </div>
    </div>
  )
}
