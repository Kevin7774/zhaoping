import { useMemo, useState } from 'react'
import JsonView from './JsonView.jsx'

const STATUS_LABEL = {
  idle: '未启动',
  pending: '队列中',
  active: '执行中',
  awaiting: '待审批',
  done: '完成',
  error: '异常',
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

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function hasLegacyStaticList(output) {
  const lists = [
    output?.目标公司,
    output?.目标团队,
    output?.优先来源,
    output?.次优来源,
    output?.候选人来源?.优先来源公司,
    output?.候选人来源?.高校实验室,
  ]
  return lists.some((list) => asArray(list).filter((item) => LEGACY_STATIC_TERMS.has(String(item))).length >= 2)
}

function safeList(list, limit = 4) {
  return asArray(list).filter((item) => !LEGACY_STATIC_TERMS.has(String(item))).slice(0, limit)
}

function compactFacts(output) {
  if (!output || typeof output !== 'object') return []
  const facts = []
  const calibration = output.校准状态 || output.候选人来源?.校准状态
  if (calibration?.status) {
    facts.push({ label: '校准', value: calibration.status })
  } else if (hasLegacyStaticList(output)) {
    facts.push({ label: '校准', value: '旧静态输出已隐藏' })
  }

  const dynamicCompanies = safeList(output.动态目标公司 || output.候选人来源?.动态目标公司)
  const dynamicLabs = safeList(output.动态实验室 || output.候选人来源?.动态实验室)
  if (dynamicCompanies.length) facts.push({ label: '动态公司', value: dynamicCompanies.join(' / ') })
  if (dynamicLabs.length) facts.push({ label: '动态实验室', value: dynamicLabs.join(' / ') })
  if (output.role_key) facts.push({ label: 'role_key', value: output.role_key })
  if (output.岗位) facts.push({ label: '岗位', value: output.岗位 })
  if (output.实时检索?.result_count !== undefined) facts.push({ label: '实时命中', value: String(output.实时检索.result_count) })
  if (output.搜索关键词?.length) facts.push({ label: '关键词', value: `${output.搜索关键词.length} 个` })
  if (output.推荐信源?.length) facts.push({ label: '信源', value: `${output.推荐信源.length} 类` })
  if (output.证据记录?.length) facts.push({ label: '证据', value: `${output.证据记录.length} 条` })
  return facts.slice(0, 5)
}

function OutputSummary({ output, onOpen }) {
  const facts = useMemo(() => compactFacts(output), [output])
  const legacy = hasLegacyStaticList(output)
  return (
    <div className={`flow-output-compact ${legacy ? 'flow-output-warning' : ''}`}>
      <div className="flow-output-compact-head">
        <span>{legacy ? '旧静态输出已收起' : '结构化输出摘要'}</span>
        <button type="button" onClick={onOpen}>
          查看详情
        </button>
      </div>
      {facts.length > 0 ? (
        <div className="flow-output-facts">
          {facts.map((fact) => (
            <div className="flow-output-fact" key={`${fact.label}-${fact.value}`}>
              <span>{fact.label}</span>
              <strong>{fact.value}</strong>
            </div>
          ))}
        </div>
      ) : (
        <div className="flow-output-muted">输出已生成，可打开详情查看。</div>
      )}
    </div>
  )
}

function OutputModal({ item, onClose }) {
  const [scale, setScale] = useState(1)
  if (!item) return null
  return (
    <div className="flow-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="flow-modal-title">
      <div className="flow-modal">
        <div className="flow-modal-head">
          <div>
            <span>步骤输出</span>
            <h3 id="flow-modal-title">{item.label}</h3>
          </div>
          <div className="flow-modal-tools">
            <button type="button" onClick={() => setScale((value) => Math.max(0.82, Number((value - 0.08).toFixed(2))))}>
              缩小
            </button>
            <strong>{Math.round(scale * 100)}%</strong>
            <button type="button" onClick={() => setScale((value) => Math.min(1.3, Number((value + 0.08).toFixed(2))))}>
              放大
            </button>
            <button type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="flow-modal-body">
          <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: `${100 / scale}%` }}>
            <JsonView value={item.output} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AgentFlow({ nodes }) {
  const [modalItem, setModalItem] = useState(null)
  return (
    <div className="agent-flow">
      {nodes.map((node, index) => {
        const agent = node.agent || {}
        const state = node.status || 'idle'
        const output = node.output
        const stepNumber = String(index + 1).padStart(2, '0')
        const modalPayload = {
          label: `${stepNumber} · ${node.label}`,
          output,
        }
        return (
          <div className={`flow-node state-${state} kind-${node.kind}`} key={`${node.agent_id}-${index}`}>
            <div className="flow-rail">
              <div className="flow-dot" aria-label={`步骤 ${index + 1}`}>
                {stepNumber}
              </div>
              {index < nodes.length - 1 && <div className="flow-line" />}
            </div>
            <div className="flow-card">
              <div className="flow-head">
                <span className="flow-agent">{agent.name_zh || node.agent_id}</span>
                <span className={`flow-badge badge-${state}`}>{STATUS_LABEL[state]}</span>
              </div>
              <div className="flow-label">{node.label} · {node.message}</div>
              {state === 'active' && (
                <div className="flow-thinking">
                  <span className="dot" /><span className="dot" /><span className="dot" />
                  <span>{agent.output_format || node.label}</span>
                </div>
              )}
              {state === 'pending' && <div className="flow-shadow">{agent.output_format || '等待上游事件'}</div>}
              {output !== undefined && output !== null && (
                <OutputSummary output={output} onOpen={() => setModalItem(modalPayload)} />
              )}
            </div>
          </div>
        )
      })}
      <OutputModal item={modalItem} onClose={() => setModalItem(null)} />
    </div>
  )
}
