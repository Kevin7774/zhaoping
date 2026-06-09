import { ARTIFACT_LABELS } from '../../agent/sharedContext.js'

function labelList(keys) {
  if (!keys?.length) return '无'
  return keys.map((key) => ARTIFACT_LABELS[key] || key).join('、')
}

export default function ModuleCallCard({ call, disabled, onContinue, onDismiss }) {
  return (
    <article className={`module-call-card risk-${call.riskLevel}`}>
      <div className="module-call-main">
        <div>
          <span className="module-call-kicker">可执行动作</span>
          <strong>{call.title}</strong>
        </div>
        <span className="module-risk">{call.riskLevel === 'low' ? '可直接执行' : '需要审批'}</span>
      </div>
      <p>{call.reason}</p>
      <div className="module-call-facts">
        <span>复用：{labelList(call.reusableInputs)}</span>
        <span>缺失：{labelList(call.missingInputs)}</span>
      </div>
      <div className="module-call-actions">
        <button className="btn btn-run" type="button" disabled={disabled} onClick={() => onContinue(call)}>
          {call.riskLevel === 'low' ? '执行动作' : '发起审批'}
        </button>
        <button className="btn btn-ghost" type="button" disabled={disabled} onClick={() => onDismiss(call)}>
          不执行
        </button>
      </div>
    </article>
  )
}
