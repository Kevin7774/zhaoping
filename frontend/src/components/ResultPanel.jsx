import JsonView from './JsonView.jsx'

export default function ResultPanel({ task }) {
  if (!task) {
    return <div className="result-empty">选择场景、输入需求并运行后，最终结构化报告会显示在这里。</div>
  }
  if (task.status === 'error') {
    return <div className="result-error">流程终止：{task.error || '未知错误'}</div>
  }
  if (task.status !== 'done' || !task.result) {
    return <div className="result-empty">Agent 正在执行，报告生成后展示真实结果…</div>
  }
  return (
    <div className="result-panel">
      <div className="result-tag">✅ 最终报告 · 来自后端真实计算</div>
      <JsonView value={task.result} />
    </div>
  )
}
