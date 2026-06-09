import JsonView from '../JsonView.jsx'

function summarizeArtifact(value) {
  if (value === null || value === undefined || value === '') return '待同步'
  if (Array.isArray(value)) {
    const sample = value
      .slice(0, 3)
      .map((item) => {
        if (typeof item === 'string' || typeof item === 'number') return String(item)
        if (item && typeof item === 'object') return item.name || item.title || item.label || item.source_key
        return null
      })
      .filter(Boolean)
      .join(' / ')
    return sample ? `${value.length} 项 · ${sample}` : `${value.length} 项`
  }
  if (typeof value === 'object') {
    const title = value.title || value.name || value.status || value.role_key
    return title ? String(title) : `${Object.keys(value).length} 个字段`
  }
  return String(value).length > 96 ? `${String(value).slice(0, 96)}...` : String(value)
}

export default function ArtifactCard({ artifact }) {
  const hasValue = artifact.value !== null && artifact.value !== undefined && artifact.value !== ''

  return (
    <article className={`artifact-card ${hasValue ? 'artifact-filled' : 'artifact-empty'}`}>
      <div className="artifact-head">
        <strong>{artifact.label}</strong>
        <span>{hasValue ? '已同步' : '待同步'}</span>
      </div>
      <p>{summarizeArtifact(artifact.value)}</p>
      {hasValue && (
        <details className="artifact-raw">
          <summary>查看数据</summary>
          <JsonView value={artifact.value} />
        </details>
      )}
    </article>
  )
}
