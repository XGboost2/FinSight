import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { FileText, MessageCircle, Loader, ChevronRight } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SAMPLE_QUESTIONS = [
  'What are the main risk factors?',
  'Summarise the revenue and earnings trend.',
  'What does management say about future outlook?',
]

const MODELS = [
  { value: 'auto',               label: 'Auto',             group: 'DeepSeek' },
  { value: 'deepseek-chat',      label: 'DS Chat',          group: 'DeepSeek' },
  { value: 'deepseek-reasoner',  label: 'DS Reasoner',      group: 'DeepSeek' },
  { value: 'claude-haiku-4-5',   label: 'Haiku',            group: 'Anthropic' },
  { value: 'claude-sonnet-4-6',  label: 'Sonnet',           group: 'Anthropic' },
  { value: 'claude-opus-4-7',    label: 'Opus',             group: 'Anthropic' },
  { value: 'gpt-4o-mini',        label: 'GPT-4o Mini',      group: 'OpenAI' },
  { value: 'gpt-4o',             label: 'GPT-4o',           group: 'OpenAI' },
]

export default function FilingPanel({ ticker, companyName, filingId, filing, fetchingFiling }) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState([])
  const [chatLoading, setChatLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState('auto')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, chatLoading])

  useEffect(() => {
    setHistory([])
    setQuestion('')
  }, [filingId])

  const send = async (q) => {
    const text = q.trim()
    if (!text || !filingId || chatLoading) return
    setQuestion('')
    setHistory(h => [...h, { role: 'user', text }])
    setChatLoading(true)

    try {
      const { data } = await axios.post(`${API_URL}/api/chat`, {
        question: text,
        ticker: ticker,
        model: selectedModel === 'auto' ? null : selectedModel,
      })
      setHistory(h => [...h, {
        role: 'assistant',
        text: data.answer,
        meta: `${data.model_used} · $${data.cost_usd.toFixed(4)} · ${Math.round(data.latency_ms)}ms`,
      }])
    } catch (e) {
      setHistory(h => [...h, {
        role: 'error',
        text: e.response?.data?.detail || 'Request failed — check backend logs.',
      }])
    } finally {
      setChatLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    send(question)
  }

  return (
    <div className="filing-panel glass-card">
      <div className="panel-header">
        <FileText size={18} />
        <h2>10-K Filing</h2>
      </div>

      {!ticker && (
        <p className="panel-empty">
          Search for a company to load its latest SEC 10-K filing and chat with it.
        </p>
      )}

      {fetchingFiling && (
        <div className="filing-loading">
          <Loader size={16} className="spin" />
          <span>Fetching SEC EDGAR 10-K for <strong>{ticker}</strong>…</span>
        </div>
      )}

      {filing && !fetchingFiling && (
        <>
          <div className="filing-meta">
            {[
              ['Company', filing.company_name || companyName],
              ['Type', filing.filing_type],
              ['Filed', filing.filed_date || '—'],
              ['Indexed', `${filing.chunk_count} chunks`],
            ].map(([label, value]) => (
              <div key={label} className="meta-row">
                <span className="meta-label">{label}</span>
                <span className={`meta-value${label === 'Type' ? ' badge' : ''}`}>{value}</span>
              </div>
            ))}
          </div>

          <div className="divider" />

          <div className="chat-area">
            <div className="chat-label">
              <MessageCircle size={14} />
              <span>Ask the filing</span>
            </div>

            {history.length === 0 && (
              <div className="sample-questions">
                {SAMPLE_QUESTIONS.map(q => (
                  <button key={q} className="sample-q" onClick={() => send(q)}>
                    <ChevronRight size={12} />
                    {q}
                  </button>
                ))}
              </div>
            )}

            <div className="chat-history">
              {history.map((msg, i) => (
                <div key={i} className={`msg ${msg.role}`}>
                  <p className="msg-text">{msg.text}</p>
                  {msg.meta && <span className="msg-meta">{msg.meta}</span>}
                </div>
              ))}
              {chatLoading && (
                <div className="msg assistant loading">
                  <Loader size={12} className="spin" />
                  <span>Thinking…</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="model-selector">
              {MODELS.map(m => (
                <button
                  key={m.value}
                  type="button"
                  className={`model-pill${selectedModel === m.value ? ' model-pill-active' : ''}`}
                  onClick={() => setSelectedModel(m.value)}
                  title={`${m.group}: ${m.label}`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="chat-form">
              <input
                type="text"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder="Ask a question about this 10-K…"
                disabled={chatLoading}
                className="chat-input"
              />
              <button
                type="submit"
                disabled={!question.trim() || chatLoading}
                className="chat-submit"
              >
                Ask
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  )
}
