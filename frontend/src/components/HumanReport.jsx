import { useMemo, useState } from 'react'
import JsonView from './JsonView.jsx'
import MarkdownBlock from './MarkdownBlock.jsx'

function citationMap(citations) {
  return Object.fromEntries((citations || []).map((citation) => [String(citation.id), citation]))
}

function calibrationState(raw) {
  return raw?.校准状态 || raw?.候选人来源?.校准状态 || null
}

function calibrationTone(state) {
  if (!state) return 'unknown'
  return state.status === 'live_calibrated' ? 'ready' : 'warning'
}

function CalibrationNotice({ state }) {
  if (!state) return null
  const live = state.status === 'live_calibrated'
  return (
    <div className={`calibration-notice calibration-${calibrationTone(state)}`}>
      <div>
        <strong>{live ? '动态来源已校准' : '动态来源未校准'}</strong>
        <span>{state.status || 'unknown'}</span>
      </div>
      <p>
        {live
          ? `实时检索抽取到 ${state.dynamic_entity_count || 0} 个动态实体，静态种子只作为审计信息。`
          : '未抽取到可验证动态实体；静态种子不会作为目标公司或实验室名单展示。'}
      </p>
    </div>
  )
}

function Paragraph({ item, citationsById, onSelect }) {
  if (!item?.text) return null
  return (
    <p className="hr-paragraph">
      {item.text}
      {(item.citations || []).map((id) => (
        <button
          className="hr-cite"
          key={id}
          type="button"
          onClick={() => onSelect(String(id))}
          title={citationsById[String(id)]?.title || `证据 ${id}`}
        >
          {id}
        </button>
      ))}
    </p>
  )
}

function EvidenceDetail({ citation }) {
  if (!citation) return <div className="hr-evidence-empty">点击正文角标查看证据详情。</div>
  return (
    <article className="hr-evidence-card">
      <div className="hr-evidence-id">证据 {citation.id}</div>
      <h4>{citation.title || citation.source_name || citation.source_key}</h4>
      <div className="hr-evidence-meta">
        {citation.source_name && <span>{citation.source_name}</span>}
        {citation.source_key && <span>{citation.source_key}</span>}
        {citation.source_type && <span>{citation.source_type}</span>}
        {citation.validation_status && <span>{citation.validation_status}</span>}
        {citation.confidence !== null && citation.confidence !== undefined && <span>confidence {citation.confidence}</span>}
        {citation.published_at && <span>{citation.published_at}</span>}
      </div>
      {citation.snippet && <p>{citation.snippet}</p>}
      {citation.url && (
        <a href={citation.url} target="_blank" rel="noreferrer">
          打开来源
        </a>
      )}
    </article>
  )
}

export default function HumanReport({ report, raw }) {
  const citationsById = useMemo(() => citationMap(report?.citations), [report?.citations])
  const firstCitationId = report?.citations?.[0]?.id ? String(report.citations[0].id) : null
  const [activeCitationId, setActiveCitationId] = useState(firstCitationId)
  const activeCitation = activeCitationId ? citationsById[activeCitationId] : null
  const calibration = calibrationState(raw)

  return (
    <div className="human-report">
      <div className="hr-head">
        <div>
          <div className="result-tag">最终报告 · 动态证据优先</div>
          <h2>{report.title}</h2>
          {report.subtitle && <p>{report.subtitle}</p>}
        </div>
        <div className="hr-citation-count">{report.citations?.length || 0} 条证据</div>
      </div>

      <CalibrationNotice state={calibration} />

      {report.summary?.length > 0 && (
        <section className="hr-summary">
          {report.summary.map((item, index) => (
            <Paragraph item={item} citationsById={citationsById} key={index} onSelect={setActiveCitationId} />
          ))}
        </section>
      )}

      <div className="hr-layout">
        <div className="hr-body">
          {report.markdown ? (
            <MarkdownBlock markdown={report.markdown} />
          ) : (
            report.sections?.map((section, sectionIndex) => (
              <section className="hr-section" key={`${section.heading}-${sectionIndex}`}>
                <h3>{section.heading}</h3>
                {section.paragraphs?.map((item, index) => (
                  <Paragraph item={item} citationsById={citationsById} key={index} onSelect={setActiveCitationId} />
                ))}
                {section.bullets?.length > 0 && (
                  <ul>
                    {section.bullets.map((bullet, index) => (
                      <li key={index}>{bullet}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))
          )}

          {report.citations?.length > 0 && (
            <section className="hr-section hr-references">
              <h3>参考与引用</h3>
              <div className="reference-list">
                {report.citations.map((citation) => (
                  <button
                    type="button"
                    className="reference-item"
                    key={citation.id}
                    onClick={() => setActiveCitationId(String(citation.id))}
                  >
                    <span>{citation.id}</span>
                    <strong>{citation.title || citation.source_name || citation.source_key}</strong>
                    {citation.url && <em>{citation.url}</em>}
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="hr-evidence">
          <div className="hr-evidence-head">
            <span>证据详情</span>
            {activeCitationId && <strong>{activeCitationId}</strong>}
          </div>
          <EvidenceDetail citation={activeCitation} />
          {report.diagnostics?.error_count > 0 && (
            <details className="hr-diagnostics">
              <summary>检索诊断 ({report.diagnostics.error_count})</summary>
              <JsonView value={report.diagnostics.errors} />
            </details>
          )}
        </aside>
      </div>

      <details className="hr-raw">
        <summary>查看原始结构化数据</summary>
        <JsonView value={raw} />
      </details>
    </div>
  )
}
