import { ARTIFACT_LABELS } from '../../agent/sharedContext.js'
import ArtifactCard from './ArtifactCard.jsx'

function artifactList(context) {
  const artifacts = context?.artifacts || {}
  return Object.entries(ARTIFACT_LABELS).map(([key, label]) => ({
    key,
    label,
    value: artifacts[key],
  }))
}

export default function SharedContextPanel({ context, moduleHistory }) {
  const artifacts = artifactList(context)
  const filledCount = artifacts.filter((artifact) => artifact.value !== null && artifact.value !== undefined && artifact.value !== '').length

  return (
    <section className="shared-context-panel" aria-label="工作区数据">
      <div className="shared-context-head">
        <div>
          <div className="col-title">工作区数据</div>
          <p>{context?.goal || '尚未创建招聘目标'}</p>
        </div>
        <span>{filledCount}/{artifacts.length}</span>
      </div>
      <div className="context-run-strip" aria-label="模块运行历史">
        <span>运行 {moduleHistory.length}</span>
        <span>能力 {context?.selectedModules?.length || 0}</span>
        <span>审批 {context?.pendingTransfers?.length || 0}</span>
      </div>
      <div className="artifact-grid">
        {artifacts.map((artifact) => (
          <ArtifactCard artifact={artifact} key={artifact.key} />
        ))}
      </div>
    </section>
  )
}
