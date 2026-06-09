// Generic recursive renderer for the backend's structured result payloads.
// Keeps the frontend scenario-agnostic: whatever shape the backend returns,
// it renders readably without hardcoding field names.

function isPrimitive(value) {
  return value === null || typeof value !== 'object'
}

const LEGACY_STATIC_TERMS = new Set([
  'Physical Intelligence',
  'World Labs',
  '银河通用',
  '智元机器人',
  '小米物理 AI 组',
  'Stanford IRIS',
  'Berkeley BAIR',
  '北大/清华具身智能实验室',
])

function isLegacyStaticList(key, value, parent) {
  if (!Array.isArray(value)) return false
  if (parent?.校准状态?.status === 'live_calibrated') return false
  if (!['目标公司', '目标团队', '优先来源', '次优来源', '高校/实验室'].includes(key)) return false
  const hits = value.filter((item) => LEGACY_STATIC_TERMS.has(String(item)))
  return hits.length >= 2
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
      {Object.entries(value).map(([key, val]) => {
        if (isLegacyStaticList(key, val, value)) {
          return (
            <div className="jv-row" key={key}>
              <div className="jv-key">{key}</div>
              <div className="jv-val">
                <details className="jv-legacy-static">
                  <summary>旧静态输出已隐藏，不作为动态结果</summary>
                  <JsonView value={val} depth={depth + 1} />
                </details>
              </div>
            </div>
          )
        }
        if (key === '静态种子') {
          return (
            <div className="jv-row" key={key}>
              <div className="jv-key">{key}</div>
              <div className="jv-val">
                <details className="jv-static-seed">
                  <summary>仅诊断，不作为前端生成结果</summary>
                  <JsonView value={val} depth={depth + 1} />
                </details>
              </div>
            </div>
          )
        }
        return (
          <div className="jv-row" key={key}>
            <div className="jv-key">{key}</div>
            <div className="jv-val">
              <JsonView value={val} depth={depth + 1} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
