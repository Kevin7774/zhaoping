function inlineParts(text) {
  const parts = []
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g
  let lastIndex = 0
  let match = pattern.exec(text)
  while (match) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index))
    parts.push(
      <a href={match[2]} target="_blank" rel="noreferrer" key={`${match[1]}-${match.index}`}>
        {match[1]}
      </a>,
    )
    lastIndex = pattern.lastIndex
    match = pattern.exec(text)
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex))
  return parts
}

export default function MarkdownBlock({ markdown }) {
  const lines = String(markdown || '').split('\n')
  const blocks = []
  let list = []

  function flushList() {
    if (!list.length) return
    blocks.push(
      <ul className="md-list" key={`list-${blocks.length}`}>
        {list.map((item, index) => (
          <li key={index}>{inlineParts(item)}</li>
        ))}
      </ul>,
    )
    list = []
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      return
    }
    if (trimmed.startsWith('- ')) {
      list.push(trimmed.slice(2))
      return
    }
    flushList()
    if (trimmed.startsWith('# ')) {
      blocks.push(<h2 key={index}>{inlineParts(trimmed.slice(2))}</h2>)
    } else if (trimmed.startsWith('## ')) {
      blocks.push(<h3 key={index}>{inlineParts(trimmed.slice(3))}</h3>)
    } else if (trimmed.startsWith('### ')) {
      blocks.push(<h4 key={index}>{inlineParts(trimmed.slice(4))}</h4>)
    } else {
      blocks.push(<p key={index}>{inlineParts(trimmed)}</p>)
    }
  })
  flushList()

  return <div className="markdown-block">{blocks}</div>
}
