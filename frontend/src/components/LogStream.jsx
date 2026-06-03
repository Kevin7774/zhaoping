import { useEffect, useRef } from 'react'

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ''
  }
}

export default function LogStream({ logs }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="log-stream">
      <div className="log-title">实时日志</div>
      <div className="log-body">
        {(!logs || logs.length === 0) && <div className="log-empty">暂无日志，运行后实时显示 Agent 执行过程。</div>}
        {logs?.map((log, i) => (
          <div className={`log-line level-${log.level || 'info'}`} key={i}>
            <span className="log-ts">{fmtTime(log.ts)}</span>
            <span className="log-msg">{log.message}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}
