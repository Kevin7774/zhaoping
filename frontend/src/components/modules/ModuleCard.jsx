import { getModule } from '../../agent/moduleGraph.js'
import { ARTIFACT_LABELS } from '../../agent/sharedContext.js'

const STATUS_LABEL = {
  idle: '未启动',
  active: '执行中',
  awaiting: '待审批',
  done: '已完成',
}

function artifactState(context, keys) {
  const artifacts = context?.artifacts || {}
  return keys.map((key) => ({
    key,
    label: ARTIFACT_LABELS[key] || key,
    ready: Boolean(artifacts[key]),
  }))
}

export default function ModuleCard({ module, active, context, disabled, status, onSelect }) {
  const provides = artifactState(context, module.provides)
  const readyCount = provides.filter((item) => item.ready).length

  return (
    <article className={`module-card module-status-${status} ${active ? 'module-active' : ''}`}>
      <div className="module-card-head">
        <button type="button" disabled={disabled || active} onClick={() => onSelect(module.id)} aria-label={`切换到${module.title}`}>
          {module.id}
        </button>
        <div>
          <strong>{module.title}</strong>
          <span>{STATUS_LABEL[status] || status}</span>
        </div>
      </div>
      <p>{module.description}</p>
      <div className="module-artifacts">
        <span>{readyCount}/{provides.length} 输出</span>
        {provides.map((artifact) => (
          <i className={artifact.ready ? 'artifact-ready' : ''} key={artifact.key} title={artifact.label} />
        ))}
      </div>
      <div className="module-links">
        {(module.canCall || []).map((targetId) => {
          const target = getModule(targetId)
          return <span key={targetId}>{target?.title || targetId}</span>
        })}
      </div>
    </article>
  )
}
