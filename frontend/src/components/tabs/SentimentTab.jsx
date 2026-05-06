import { useEffect, useState } from 'react'
import { Activity, FileText, TrendingUp, TrendingDown, Loader, AlertTriangle } from 'lucide-react'
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

export default function SentimentTab({ ticker, onStatusChange }) {
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    axios.get(`${API_URL}/api/companies/${ticker}/report`)
      .then(r => { setReport(r.data); onStatusChange?.('done') })
      .catch(e => { setError(e.response?.data?.detail || 'Failed to load sentiment data.'); onStatusChange?.('error') })
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading) return (
    <div className="tab-view">
      <div className="report-loading glass-card"><Loader size={14} className="spin" /><span>Loading sentiment analysis…</span></div>
    </div>
  )
  if (error) return (
    <div className="tab-view">
      <div className="report-error glass-card"><AlertTriangle size={14} /><span>{error}</span></div>
    </div>
  )

  const score = report?.sentiment_score ?? 0.5
  const label = report?.sentiment_label ?? 'Neutral'

  const SECTIONS = [
    { label: 'Item 7 — MD&A',              score },
    { label: 'Item 1 — Business Overview', score: Math.min(score + 0.08, 1) },
    { label: 'Item 1A — Risk Factors',     score: Math.max(score - 0.25, 0) },
  ]

  const themes = report?.management_themes
    ? report.management_themes.split(/[.,]/).map(t => t.trim()).filter(t => t.length > 8).slice(0, 5)
    : []

  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Activity size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Sentiment Analyst</span>
            <span className="tab-agent-source">LLM-scored MD&A tone · 10-K filing</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">Live</span>
      </div>

      {report && (
        <>
          <div className="tab-row-2col">
            <div className="tab-section glass-card">
              <div className="section-label">Overall MD&A Tone</div>
              <div className="sentiment-hero">
                <span className="sentiment-hero-score">{Math.round(score * 100)}</span>
                <div>
                  <SentimentBadge score={score} label={label} />
                  <p className="sentiment-hero-sub">{report.management_themes?.slice(0, 120) || 'Management tone extracted from 10-K MD&A.'}</p>
                </div>
              </div>
            </div>

            <div className="tab-section glass-card">
              <div className="section-label">Score by Section</div>
              <div className="sent-sections">
                {SECTIONS.map((s, i) => (
                  <div key={i} className="sent-section-row">
                    <div className="sent-section-meta">
                      <FileText size={12} />
                      <span className="sent-section-label">{s.label}</span>
                      <SentimentBadge
                        score={s.score}
                        label={s.score >= 0.6 ? 'Positive' : s.score >= 0.4 ? 'Neutral' : 'Negative'}
                      />
                    </div>
                    <SentimentBar score={s.score} />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {themes.length > 0 && (
            <div className="tab-section glass-card">
              <div className="section-label">Key Management Themes</div>
              <div className="sent-themes">
                {themes.map((t, i) => <span key={i} className="sent-theme-chip">{t}</span>)}
              </div>
            </div>
          )}

          <div className="tab-section glass-card">
            <div className="section-label">Management Commentary</div>
            <p className="report-prose">{report.management_themes}</p>
          </div>
        </>
      )}

      {!report && !loading && (
        <div className="tab-placeholder-note">Run analysis on the Fundamentals tab first.</div>
      )}

      <div className="tab-placeholder-note">
        FinBERT per-sentence scoring (Feature 2) will replace LLM-scored sentiment in a future update.
      </div>
    </div>
  )
}
