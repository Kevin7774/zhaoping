import { MODULE_GRAPH, MODULE_SEQUENCE } from '../../agent/moduleGraph.js'
import ModuleCallCard from './ModuleCallCard.jsx'
import ModuleCard from './ModuleCard.jsx'

export default function ModuleGraph({
  activeModuleId,
  context,
  disabled,
  moduleStatuses,
  onDismissCall,
  onRequestCall,
  onSelectModule,
  pendingCall,
  recommendedCalls,
}) {
  return (
    <section className="module-graph-panel" aria-label="招聘能力编排">
      <div className="module-graph-head">
        <div>
          <div className="section-label">Workflow</div>
          <h2>招聘能力编排</h2>
        </div>
        <span>{pendingCall ? '审批待处理' : `${recommendedCalls.length} 个可执行动作`}</span>
      </div>

      <div className="module-graph-line" aria-hidden="true">
        {MODULE_SEQUENCE.map((moduleId, index) => (
          <span key={moduleId}>
            {moduleId}
            {index < MODULE_SEQUENCE.length - 1 && <b />}
          </span>
        ))}
      </div>

      <div className="module-card-grid">
        {MODULE_SEQUENCE.map((moduleId) => {
          const module = MODULE_GRAPH[moduleId]
          return (
            <ModuleCard
              active={activeModuleId === moduleId}
              context={context}
              disabled={disabled}
              key={moduleId}
              module={module}
              onSelect={onSelectModule}
              status={moduleStatuses[moduleId] || 'idle'}
            />
          )
        })}
      </div>

      {recommendedCalls.length > 0 && (
        <div className="module-call-list">
          {recommendedCalls.map((call) => (
            <ModuleCallCard
              call={call}
              disabled={disabled}
              key={`${call.from}-${call.to}`}
              onContinue={() => onRequestCall(call.from, call.to)}
              onDismiss={onDismissCall}
            />
          ))}
        </div>
      )}
    </section>
  )
}
