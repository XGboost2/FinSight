import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react'

const EXCERPT_LEN = 220

function CitationCard({ citation, idx }) {
  const [expanded, setExpanded] = useState(false)
  const text = citation.text ?? ''
  const truncated = text.length > EXCERPT_LEN && !expanded
  const display = truncated ? text.slice(0, EXCERPT_LEN) + '…' : text

  const sectionLabel = citation.item
    ? citation.item
    : citation.section
    ? citation.section
    : `Chunk ${citation.chunk_index ?? idx + 1}`

  return (
    <div className="citation-card glass-card">
      <div className="citation-header">
        <span className="citation-index">[{idx + 1}]</span>
        <span className="citation-section">{sectionLabel}</span>
        <span className="citation-source">SEC 10-K</span>
      </div>
      <p className="citation-text">{display}</p>
      {text.length > EXCERPT_LEN && (
        <button
          className="citation-toggle"
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Show more</>}
        </button>
      )}
    </div>
  )
}

export default function CitationPanel({ citations }) {
  const [open, setOpen] = useState(false)

  if (!citations?.length) return null

  return (
    <div className="citation-panel glass-card">
      <button className="citation-panel-toggle" onClick={() => setOpen(o => !o)}>
        <div className="citation-panel-title">
          <BookOpen size={13} />
          <span>Source Citations</span>
          <span className="citation-count">{citations.length} chunks</span>
        </div>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {open && (
        <div className="citation-list">
          {citations.map((c, i) => (
            <CitationCard key={c.chunk_index ?? i} citation={c} idx={i} />
          ))}
        </div>
      )}
    </div>
  )
}
