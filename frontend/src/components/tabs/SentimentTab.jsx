import { Activity, FileText, TrendingUp, TrendingDown } from 'lucide-react'

const SECTIONS = [
  { label: 'Item 7 — MD&A',              score: 0.68, label_text: 'Positive' },
  { label: 'Item 1 — Business Overview', score: 0.55, label_text: 'Neutral'  },
  { label: 'Item 1A — Risk Factors',     score: 0.32, label_text: 'Negative' },
]

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

export default function SentimentTab({ ticker }) {
  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Activity size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Sentiment Analyst</span>
            <span className="tab-agent-source">FinBERT · ProsusAI · MD&A tone analysis</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-pending">Backend pending</span>
      </div>

      <div className="tab-row-2col">
        <div className="tab-section glass-card">
          <div className="section-label">Overall MD&A Tone</div>
          <div className="sentiment-hero">
            <span className="sentiment-hero-score">68</span>
            <div>
              <span className="sentiment-badge sentiment-positive">Positive</span>
              <p className="sentiment-hero-sub">Management tone leans optimistic. Confidence in near-term outlook.</p>
            </div>
          </div>
        </div>

        <div className="tab-section glass-card">
          <div className="section-label">YoY Tone Shift</div>
          <div className="sent-yoy-row">
            <div className="sent-yoy-item">
              <span className="sent-yoy-year">Prior year</span>
              <span className="sent-yoy-val">61/100</span>
            </div>
            <TrendingUp size={16} className="sent-yoy-arrow sent-yoy-up" />
            <div className="sent-yoy-item">
              <span className="sent-yoy-year">This year</span>
              <span className="sent-yoy-val">68/100</span>
            </div>
          </div>
          <p className="report-prose report-prose-sm">Management language is measurably more positive this year — fewer hedging phrases in the MD&A.</p>
        </div>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">Score by Filing Section</div>
        <div className="sent-sections">
          {SECTIONS.map((s, i) => (
            <div key={i} className="sent-section-row">
              <div className="sent-section-meta">
                <FileText size={12} />
                <span className="sent-section-label">{s.label}</span>
                <span className={`sentiment-badge ${
                  s.score >= 0.6 ? 'sentiment-positive' : s.score >= 0.4 ? 'sentiment-neutral' : 'sentiment-negative'
                }`}>{s.label_text}</span>
              </div>
              <SentimentBar score={s.score} />
            </div>
          ))}
        </div>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">Key Themes from MD&A</div>
        <div className="sent-themes">
          {['Revenue growth confidence', 'Cost discipline emphasis', 'Regulatory headwinds acknowledged', 'AI investment acceleration'].map((t, i) => (
            <span key={i} className="sent-theme-chip">{t}</span>
          ))}
        </div>
      </div>

      <div className="tab-placeholder-note">
        FinBERT (ProsusAI/finbert, 110M params) will run on Item 7 chunks when the Sentiment Analyst is connected.
      </div>
    </div>
  )
}
