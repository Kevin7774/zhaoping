import JsonView from './JsonView.jsx'
import HumanReport from './HumanReport.jsx'
import DecisionSandbox from './DecisionSandbox.jsx'

export default function ResultPanel({ task, teamConstraint, apertureWeight }) {
  if (!task) {
    return <div className="result-empty">暂无任务。</div>
  }
  if (task.status === 'error') {
    return <div className="result-error">流程终止：{task.error || '未知错误'}</div>
  }
  if (task.status === 'cancelled') {
    return <div className="result-error">任务已取消：{task.error || '用户取消任务'}</div>
  }
  if (task.status !== 'done' || !task.result) {
    return <div className="result-empty">交付报告未生成</div>
  }
  const humanReport = task.result.human_report
  if (task.scenario === 'C' && task.result.decision_sandbox) {
    return (
      <div className="result-panel result-panel-wide">
        <DecisionSandbox task={task} teamConstraint={teamConstraint} apertureWeight={apertureWeight} />
        {humanReport && (
          <details className="hr-raw">
            <summary>分析报告</summary>
            <HumanReport report={humanReport} raw={task.result} />
          </details>
        )}
      </div>
    )
  }
  return (
    <div className="result-panel">
      {humanReport ? (
        <HumanReport report={humanReport} raw={task.result} />
      ) : (
        <>
          <div className="result-tag">交付报告 · 后端计算结果</div>
          <JsonView value={task.result} />
        </>
      )}
    </div>
  )
}
