import JsonView from '../JsonView.jsx'

const WORKSPACE_ARTIFACTS = {
  search: ['search_plan', 'search_results', 'evidence_records', 'intel_brief'],
  archive: ['archive_record', 'watchlist_run'],
  candidate: ['resume_ingest', 'candidate_matches'],
  evaluation: ['rsi_report'],
}

function artifactSummary(artifact) {
  const data = artifact.data
  if (!data || typeof data !== 'object') return String(data || '无数据')
  if (data.query) return data.query
  if (data.candidate_id) return data.candidate_id
  if (data.status) return data.status
  if (data.summary?.case_count) return `${data.summary.case_count} cases`
  if (Array.isArray(data.results)) return `${data.results.length} results`
  return `${Object.keys(data).length} fields`
}

function ArtifactList({ artifacts, emptyLabel }) {
  if (!artifacts.length) return <div className="workspace-empty">{emptyLabel}</div>
  return (
    <div className="workspace-artifact-list">
      {artifacts.map((artifact) => (
        <article className="workspace-artifact" key={artifact.id}>
          <div className="workspace-artifact-head">
            <div>
              <span>{artifact.type}</span>
              <strong>{artifact.title}</strong>
            </div>
            <small>{new Date(artifact.createdAt).toLocaleTimeString()}</small>
          </div>
          <p>{artifactSummary(artifact)}</p>
          <details>
            <summary>查看 JSON</summary>
            <JsonView value={artifact.data} />
          </details>
        </article>
      ))}
    </div>
  )
}

function latestByType(artifacts, type) {
  return artifacts.find((artifact) => artifact.type === type)?.data || null
}

function firstList(...values) {
  return values.find((value) => Array.isArray(value) && value.length) || []
}

function SearchPlanPreview({ plan }) {
  if (!plan) return <div className="workspace-empty">暂无搜索计划。</div>
  const constraints = firstList(plan.constraints, plan.guardrails, plan.query_constraints)
  const dataSources = firstList(plan.data_sources, plan.sources, plan.source_catalog)
  return (
    <article className="intel-preview">
      <div className="intel-preview-head">
        <span>search_plan</span>
        <strong>{plan.query || plan.search_query || '未命名 query'}</strong>
      </div>
      <div className="intel-kv-grid">
        <span>limit</span>
        <strong>{plan.limit || plan.result_limit || 'default'}</strong>
        <span>service</span>
        <strong>{plan.service || plan.provider || 'default'}</strong>
        <span>数据源</span>
        <strong>{dataSources.length ? dataSources.slice(0, 4).map((item) => item.name || item.source_key || item).join(' / ') : '默认源'}</strong>
        <span>约束</span>
        <strong>{constraints.length ? constraints.slice(0, 3).join(' / ') : '无额外约束'}</strong>
      </div>
    </article>
  )
}

function SearchResultsPreview({ results }) {
  const rows = firstList(results?.results, results?.records, results)
  if (!rows.length) return <div className="workspace-empty">暂无搜索结果。</div>
  return (
    <article className="intel-preview">
      <div className="intel-preview-head">
        <span>search_results</span>
        <strong>{rows.length} 条结果</strong>
      </div>
      <div className="intel-table">
        <div className="intel-table-row intel-table-head">
          <span>标题</span>
          <span>来源</span>
          <span>摘要</span>
        </div>
        {rows.slice(0, 8).map((row, index) => (
          <div className="intel-table-row" key={row.record_id || row.url || `${row.title}-${index}`}>
            <span>{row.title || row.name || row.url || `结果 ${index + 1}`}</span>
            <span>{row.source_key || row.source || row.source_type || 'unknown'}</span>
            <span>{row.summary || row.snippet || row.description || row.url || '无摘要'}</span>
          </div>
        ))}
      </div>
    </article>
  )
}

function EvidencePreview({ evidence }) {
  const rows = firstList(evidence?.records, evidence?.evidence_records, evidence?.priority_evidence, evidence)
  if (!rows.length) return <div className="workspace-empty">暂无证据链。</div>
  return (
    <article className="intel-preview">
      <div className="intel-preview-head">
        <span>evidence_records</span>
        <strong>{rows.length} 条证据</strong>
      </div>
      <div className="intel-table intel-evidence-table">
        <div className="intel-table-row intel-table-head">
          <span>claim</span>
          <span>record_id</span>
          <span>source tier</span>
          <span>交叉验证</span>
        </div>
        {rows.slice(0, 8).map((row, index) => (
          <div className="intel-table-row" key={row.record_id || row.id || index}>
            <span>{row.claim || evidence?.claim || '待人工审核'}</span>
            <span>{row.record_id || row.id || `ev_${index + 1}`}</span>
            <span>{row.source_tier || row.tier || row.source_type || 'unknown'}</span>
            <span>{row.cross_validation?.status || row.validation_status || row.status || 'needs_review'}</span>
          </div>
        ))}
      </div>
    </article>
  )
}

function BriefPreview({ brief }) {
  if (!brief) return <div className="workspace-empty">暂无情报简报。</div>
  const priorityEvidence = firstList(brief.priority_evidence, brief.evidence_review?.priority_evidence)
  const coverage = brief.coverage_matrix || brief.executive_summary?.source_tier_counts || {}
  return (
    <article className="intel-preview">
      <div className="intel-preview-head">
        <span>intel_brief</span>
        <strong>{brief.executive_summary?.status || brief.status || brief.brief_type || 'brief'}</strong>
      </div>
      <p>{brief.executive_summary?.summary || brief.executive_summary?.decision || brief.summary || '简报已生成，等待人工审阅。'}</p>
      <div className="intel-kv-grid">
        <span>priority evidence</span>
        <strong>{priorityEvidence.length ? priorityEvidence.slice(0, 3).map((item) => item.source_key || item.title || item.record_id).join(' / ') : '无'}</strong>
        <span>coverage matrix</span>
        <strong>{Object.keys(coverage).length ? Object.entries(coverage).slice(0, 4).map(([key, value]) => `${key}:${value}`).join(' / ') : '无'}</strong>
      </div>
    </article>
  )
}

function SearchIntelWorkspace({ artifacts }) {
  const scoped = artifacts.filter((artifact) => WORKSPACE_ARTIFACTS.search.includes(artifact.type))
  const plan = latestByType(scoped, 'search_plan')
  const results = latestByType(scoped, 'search_results')
  const evidence = latestByType(scoped, 'evidence_records')
  const brief = latestByType(scoped, 'intel_brief')
  return (
    <section className="workspace-panel-inner" aria-label="SearchIntelWorkspace">
      <div className="workspace-panel-head">
        <div>
          <span className="section-label">SearchIntelWorkspace</span>
          <h2>搜索情报</h2>
        </div>
        <span>{scoped.length} artifacts</span>
      </div>
      <div className="workspace-matrix">
        <span>搜索计划</span>
        <span>搜索结果</span>
        <span>证据链</span>
        <span>简报</span>
      </div>
      <div className="intel-preview-grid">
        <SearchPlanPreview plan={plan} />
        <SearchResultsPreview results={results} />
        <EvidencePreview evidence={evidence} />
        <BriefPreview brief={brief} />
      </div>
      <ArtifactList artifacts={scoped} emptyLabel="暂无搜索 artifact。" />
    </section>
  )
}

function ArchiveWatchWorkspace({ artifacts }) {
  const scoped = artifacts.filter((artifact) => WORKSPACE_ARTIFACTS.archive.includes(artifact.type))
  return (
    <section className="workspace-panel-inner" aria-label="ArchiveWatchWorkspace">
      <div className="workspace-panel-head">
        <div>
          <span className="section-label">ArchiveWatchWorkspace</span>
          <h2>归档与 Watchlist</h2>
        </div>
        <span>{scoped.length} artifacts</span>
      </div>
      <div className="workspace-matrix">
        <span>recent</span>
        <span>diff</span>
        <span>watchlist</span>
        <span>归档确认</span>
      </div>
      <ArtifactList artifacts={scoped} emptyLabel="暂无归档或 watchlist artifact。" />
    </section>
  )
}

function CandidateWorkspace({ artifacts }) {
  const scoped = artifacts.filter((artifact) => WORKSPACE_ARTIFACTS.candidate.includes(artifact.type))
  return (
    <section className="workspace-panel-inner" aria-label="CandidateWorkspace">
      <div className="workspace-panel-head">
        <div>
          <span className="section-label">CandidateWorkspace</span>
          <h2>候选人数据</h2>
        </div>
        <span>{scoped.length} artifacts</span>
      </div>
      <div className="workspace-matrix">
        <span>resume ingest</span>
        <span>job match</span>
        <span>score</span>
        <span>metadata</span>
      </div>
      <ArtifactList artifacts={scoped} emptyLabel="暂无候选人 artifact。" />
    </section>
  )
}

function EvaluationWorkspace({ artifacts }) {
  const scoped = artifacts.filter((artifact) => WORKSPACE_ARTIFACTS.evaluation.includes(artifact.type))
  return (
    <section className="workspace-panel-inner" aria-label="EvaluationWorkspace">
      <div className="workspace-panel-head">
        <div>
          <span className="section-label">EvaluationWorkspace</span>
          <h2>评估实验室</h2>
        </div>
        <span>{scoped.length} artifacts</span>
      </div>
      <div className="workspace-matrix">
        <span>pass/fail</span>
        <span>threshold</span>
        <span>local/full</span>
        <span>live risk</span>
      </div>
      <ArtifactList artifacts={scoped} emptyLabel="暂无 RSI report。" />
    </section>
  )
}

export default function WorkspaceTabs({ artifacts, opsPanel, selectedWorkspace, workflowPanel }) {
  return (
    <section className="workspace-tabs-panel" aria-label="辅助工作台">
      {selectedWorkspace === 'workflow' && workflowPanel}
      {selectedWorkspace === 'search' && <SearchIntelWorkspace artifacts={artifacts} />}
      {selectedWorkspace === 'archive' && <ArchiveWatchWorkspace artifacts={artifacts} />}
      {selectedWorkspace === 'candidate' && <CandidateWorkspace artifacts={artifacts} />}
      {selectedWorkspace === 'evaluation' && <EvaluationWorkspace artifacts={artifacts} />}
      {selectedWorkspace === 'ops' && opsPanel}
    </section>
  )
}
