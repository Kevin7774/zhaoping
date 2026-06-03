// Generic recursive renderer for the backend's structured result payloads.
// Keeps the frontend scenario-agnostic: whatever shape the backend returns,
// it renders readably without hardcoding field names.

function isPrimitive(value) {
  return value === null || typeof value !== 'object'
}

function Primitive({ value }) {
  if (value === null || value === undefined) return <span className="jv-null">—</span>
  if (typeof value === 'boolean') return <span className="jv-bool">{value ? '是' : '否'}</span>
  if (typeof value === 'number') return <span className="jv-num">{value}</span>
  return <span className="jv-str">{String(value)}</span>
}

export default function JsonView({ value, depth = 0 }) {
  if (isPrimitive(value)) return <Primitive value={value} />

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="jv-null">（空）</span>
    const allPrimitive = value.every(isPrimitive)
    if (allPrimitive) {
      return (
        <div className="jv-chips">
          {value.map((item, i) => (
            <span className="jv-chip" key={i}>
              {String(item)}
            </span>
          ))}
        </div>
      )
    }
    return (
      <div className="jv-list">
        {value.map((item, i) => (
          <div className="jv-list-item" key={i}>
            <JsonView value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className={`jv-object depth-${Math.min(depth, 3)}`}>
      {Object.entries(value).map(([key, val]) => (
        <div className="jv-row" key={key}>
          <div className="jv-key">{key}</div>
          <div className="jv-val">
            <JsonView value={val} depth={depth + 1} />
          </div>
        </div>
      ))}
    </div>
  )
}
