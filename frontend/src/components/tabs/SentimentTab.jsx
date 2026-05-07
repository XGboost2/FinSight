import { useEffect, useState } from 'react'
import { Activity, FileText, Loader, AlertTriangle } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function SentimentBar({ score }) {
  const pct = Math.round(score * 100)
  const cls = score >= 0.6 ? 'sent-bar-pos' : score >= 0.4 ? 'sent-bar-neu' : 'sent-bar-neg'
  return (
    <div className="sent-bar-wrap">
      <div className="sent-bar-track">
        <div className={`sent-bar-fill ${cls}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="sent-bar-value">{pct}/100</span>
    </div>
  )
}

function SentimentBadge({ score, label }) {
  const cls = score >= 0.6 ? 'sentiment-positive' : score >= 0.4 ? 'sentiment-neutral' : 'sentiment-negative'
  return <span className={`sentiment-badge ${cls}`}>{label}</span>
}

const LABEL_STYLES = {
  positive: 'sent-sentence-pos',
  negative: 'sent-sentence-neg',
  neutral:  'sent-sentence-neu',
}

export default function SentimentTab({ ticker, onStatusChange }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    axios.get(`${API_URL}/api/companies/${ticker}/sentiment`)
      .then(r => { setData(r.data); onStatusChange?.('done') })
      .catch(e => { setError(e.response?.data?.detail || 'Failed to load sentiment.'); onStatusChange?.('error') })
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading) return (
    <div className="tab-view">
      <div className="report-loading glass-card"><Loader size={14} className="spin" /><span>Running FinBERT on MD&A…</span></div>
    </div>
  )
  if (error) return (
    <div className="tab-view">
      <div className="report-error glass-card"><AlertTriangle size={14} /><span>{error}</span></div>
    </div>
  )

  const score = data?.score ?? 0.5
  const label = data?.label ?? 'Neutral'

  const breakdown = data ? [
    { label: 'Positive',  score: data.avg_positive },
    { label: 'Neutral',   score: data.avg_neutral  },
    { label: 'Negative',  score: data.avg_negative },
  ] : []

  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Activity size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Sentiment Analyst</span>
            <span className="tab-agent-source">ProsusAI/finbert · Item 7 MD&A · {data?.chunk_count ?? 0} chunks</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">FinBERT</span>
      </div>

      {data && (
        <>
          <div className="tab-row-2col">
            <div className="tab-section glass-card">
              <div className="section-label">Overall MD&A Tone</div>
              <div className="sentiment-hero">
                <span className="sentiment-hero-score">{Math.round(score * 100)}</span>
                <div>
                  <SentimentBadge score={score} label={label} />
                  <p className="sentiment-hero-sub">{data.source}</p>
                </div>
              </div>
            </div>

            <div className="tab-section glass-card">
              <div className="section-label">Class Probabilities</div>
              <div className="sent-sections">
                {breakdown.map((b, i) => (
                  <div key={i} className="sent-section-row">
                    <div className="sent-section-meta">
                      <FileText size={12} />
                      <span className="sent-section-label">{b.label}</span>
                    </div>
                    <SentimentBar score={b.score} />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {data.top_sentences?.length > 0 && (
            <div className="tab-section glass-card">
              <div className="section-label">Most Polarised Sentences</div>
              <div className="sent-sentences">
                {data.top_sentences.map((s, i) => (
                  <div key={i} className={`sent-sentence ${LABEL_STYLES[s.label] || ''}`}>
                    <span className="sent-sentence-label">{s.label}</span>
                    <p className="sent-sentence-text">{s.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {!data && !loading && (
        <div className="tab-placeholder-note">Run analysis on the Fundamentals tab first.</div>
      )}
    </div>
  )
}
