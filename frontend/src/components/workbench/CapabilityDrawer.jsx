import { useMemo, useState } from 'react'
import { WORKSPACES, productizationSummary } from '../../capabilities/capabilityRegistry.js'

function statusLabel(status) {
  if (status === 'productized') return '已产品化'
  if (status === 'system') return '系统能力'
  if (status === 'closed') return '暂不开放'
  return status
}

export default function CapabilityDrawer({
  capabilities,
  currentSuggestions,
  onRequestCapability,
  onSelectWorkspace,
  pathProductization,
  selectedWorkspace,
}) {
  const [query, setQuery] = useState('')
  const [workspaceFilter, setWorkspaceFilter] = useState('all')
  const summary = productizationSummary()
  const filteredCapabilities = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return capabilities.filter((capability) => {
      const matchesWorkspace = workspaceFilter === 'all' || capability.workspace === workspaceFilter
      const haystack = [capability.id, capability.title, capability.description, capability.workspace].join(' ').toLowerCase()
      return matchesWorkspace && (!normalized || haystack.includes(normalized))
    })
  }, [capabilities, query, workspaceFilter])

  return (
    <aside className="capability-drawer" aria-label="能力抽屉">
      <div className="drawer-head">
        <div>
          <span className="section-label">Capability Drawer</span>
          <h2>能力抽屉</h2>
        </div>
        <span>{capabilities.length} cards</span>
      </div>

      <nav className="workspace-nav" aria-label="工作台导航">
        {WORKSPACES.filter((workspace) => workspace.id !== 'chat').map((workspace) => (
          <button
            className={selectedWorkspace === workspace.id ? 'workspace-active' : ''}
            key={workspace.id}
            type="button"
            onClick={() => onSelectWorkspace(workspace.id)}
          >
            <span>{workspace.label}</span>
            <small>{workspace.title}</small>
          </button>
        ))}
      </nav>

      <section className="drawer-section">
        <div className="drawer-section-head">
          <strong>当前输入可用能力</strong>
          <span>{currentSuggestions.length}</span>
        </div>
        <div className="drawer-mini-list">
          {currentSuggestions.map((capability) => (
            <button type="button" key={capability.id} onClick={() => onRequestCapability(capability)}>
              <span>{capability.title}</span>
              <small>{capability.requiresConfirmation ? 'requiresConfirmation' : 'read-only'}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="drawer-section">
        <div className="drawer-section-head">
          <strong>全部能力目录</strong>
          <span>{filteredCapabilities.length}</span>
        </div>
        <div className="drawer-controls">
          <input
            aria-label="搜索能力"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索能力"
          />
          <select value={workspaceFilter} onChange={(event) => setWorkspaceFilter(event.target.value)} aria-label="筛选工作台">
            <option value="all">全部</option>
            {WORKSPACES.filter((workspace) => workspace.id !== 'chat').map((workspace) => (
              <option key={workspace.id} value={workspace.id}>{workspace.label}</option>
            ))}
          </select>
        </div>
        <div className="drawer-capability-list">
          {filteredCapabilities.map((capability) => (
            <article className="drawer-capability-card" key={capability.id}>
              <div>
                <span>{capability.workspace}</span>
                <strong>{capability.title}</strong>
              </div>
              <p>{capability.description}</p>
              <div className="drawer-card-meta">
                <span>{capability.requiresConfirmation ? 'requiresConfirmation' : 'read-only'}</span>
                <span>{capability.writeScope === 'none' ? '不写入' : `写入 ${capability.writeScope}`}</span>
                <span>{capability.riskLevel}</span>
              </div>
              <button className="btn btn-ghost" type="button" onClick={() => onRequestCapability(capability)}>
                调用
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="drawer-section">
        <div className="drawer-section-head">
          <strong>路径产品化状态</strong>
          <span>{summary.productized || 0}/{Object.keys(pathProductization).length}</span>
        </div>
        <div className="path-status-list">
          {Object.entries(pathProductization).map(([path, status]) => (
            <div key={path}>
              <code>{path}</code>
              <span className={`path-status status-${status}`}>{statusLabel(status)}</span>
            </div>
          ))}
        </div>
      </section>
    </aside>
  )
}
