import { useEffect, useRef } from 'react'

function fmtTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ''
  }
}

export default function LogStream({ logs }) {
  const bodyRef = useRef(null)
  const stickToBottomRef = useRef(true)

  useEffect(() => {
    const body = bodyRef.current
    if (!body || !stickToBottomRef.current) return
    body.scrollTop = body.scrollHeight
  }, [logs?.length])

  function handleScroll() {
    const body = bodyRef.current
    if (!body) return
    const distanceToBottom = body.scrollHeight - body.scrollTop - body.clientHeight
    stickToBottomRef.current = distanceToBottom < 24
  }

  return (
    <div className="log-stream">
      <div className="log-title">执行事件</div>
      <div className="log-body" ref={bodyRef} onScroll={handleScroll}>
        {(!logs || logs.length === 0) && <div className="log-empty">无执行事件</div>}
        {logs?.map((log, i) => (
          <div className={`log-line level-${log.level || 'info'}`} key={i}>
            <span className="log-ts">{fmtTime(log.ts)}</span>
            <span className="log-msg">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
