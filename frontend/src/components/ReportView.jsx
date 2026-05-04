import { useEffect, useState } from 'react'
import axios from 'axios'
import { FileBarChart, Loader, RefreshCw, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Minus } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SIGNAL_CONFIG = {
  positive: { cls: 'signal-positive', icon: '✅', label: 'Positive' },
  caution:  { cls: 'signal-caution',  icon: '⚠️', label: 'Caution'  },
  negative: { cls: 'signal-negative', icon: '🔴', label: 'Risk'     },
  neutral:  { cls: 'signal-neutral',  icon: 'ℹ️', label: 'Neutral'  },
}

function SignalBadge({ signal }) {
  const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.neutral
  return <span className={`signal-badge ${cfg.cls}`}>{cfg.icon} {cfg.label}</span>
}

function RiskGauge({ score }) {
  const pct = Math.round(score * 100)
  const label = score < 0.3 ? 'Low' : score < 0.6 ? 'Moderate' : 'High'
  const cls = score < 0.3 ? 'gauge-low' : score < 0.6 ? 'gauge-moderate' : 'gauge-high'
  return (
    <div className="risk-gauge">
      <div className="gauge-track">
        <div className={`gauge-fill ${cls}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`gauge-label ${cls}`}>{label} · {pct}/100</span>
    </div>
  )
}

function SentimentBadge({ score, label }) {
  const cls = score >= 0.6 ? 'sentiment-positive' : score >= 0.4 ? 'sentiment-neutral' : 'sentiment-negative'
  return <span className={`sentiment-badge ${cls}`}>{label}</span>
}

export default function ReportView({ ticker, compact = false, ingesting = false }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchReport = async (refresh = false) => {
    if (!ticker || ingesting) return
    setLoading(true)
    setError(null)
    try {
      const { data } = await axios.get(
        `${API_URL}/api/companies/${ticker}/report${refresh ? '?refresh=true' : ''}`
      )
      setReport(data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to generate report.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchReport() }, [ticker, ingesting])

  if (!ticker) return null

  if (ingesting || loading) return (
    <div className="report-loading glass-card">
      <Loader size={16} className="spin" />
      <span>{ingesting ? 'Fetching 10-K filing…' : 'Generating analysis report — first load takes 10-15s…'}</span>
    </div>
  )

  if (error) return (
    <div className="report-loading glass-card">
      <Loader size={16} className="spin" />
      <span>Preparing report — retrying…</span>
    </div>
  )

  if (!report) return null
  if (report.error) return (
    <div className="report-error glass-card">
      <AlertTriangle size={14} />
      <span>Report error: {report.error}</span>
    </div>
  )

  return (
    <div className={`report-view ${compact ? 'report-compact' : ''}`}>

      {/* Header */}
      {!compact && (
        <div className="report-header glass-card">
          <div className="report-title-row">
            <FileBarChart size={16} className="report-icon" />
            <div>
              <span className="report-ticker">{report.ticker}</span>
              <span className="report-company">{report.company_name}</span>
            </div>
            <span className="report-label">10-K Fundamental Analysis</span>
          </div>
          {report.generated_at && (
            <div className="report-meta-row">
              <span className="report-generated">
                Generated {new Date(report.generated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
              </span>
              <button className="btn-refresh" onClick={() => fetchReport(true)} title="Regenerate report">
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
          )}
        </div>
      )}

      {/* Company Overview */}
      {report.company_overview && (
        <div className="report-section glass-card">
          <div className="section-label">Company Overview</div>
          <p className="report-prose">{report.company_overview}</p>
        </div>
      )}

      {/* Findings Table */}
      {report.findings_table?.length > 0 && (
        <div className="report-section glass-card">
          <div className="section-label">Detailed Findings</div>
          <div className="findings-table-wrap">
            <table className="findings-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Metric</th>
                  <th>Value</th>
                  <th>YoY</th>
                  <th>Signal</th>
                  <th>Interpretation</th>
                </tr>
              </thead>
              <tbody>
                {report.findings_table.map((row, i) => (
                  <tr key={i}>
                    <td className="finding-category">{row.category}</td>
                    <td className="finding-metric">{row.metric}</td>
                    <td className="finding-value">{row.value}</td>
                    <td className="finding-yoy">{row.yoy ?? '—'}</td>
                    <td><SignalBadge signal={row.signal} /></td>
                    <td className="finding-interp">{row.interpretation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Trend Narrative */}
      {report.trend_narrative && !compact && (
        <div className="report-section glass-card">
          <div className="section-label">Financial Trend Analysis</div>
          <p className="report-prose">{report.trend_narrative}</p>
        </div>
      )}

      {/* Risk + Sentiment row */}
      <div className="report-row-2col">
        {/* Risk Assessment */}
        <div className="report-section glass-card">
          <div className="section-label">
            <AlertTriangle size={12} /> Risk Assessment
          </div>
          <RiskGauge score={report.risk_score ?? 0} />
          {report.risk_factors?.length > 0 && (
            <ul className="risk-list-report">
              {report.risk_factors.map((r, i) => (
                <li key={i} className="risk-item-report">{r}</li>
              ))}
            </ul>
          )}
        </div>

        {/* Management Sentiment */}
        <div className="report-section glass-card">
          <div className="section-label">Management Sentiment</div>
          <div className="sentiment-row">
            <SentimentBadge score={report.sentiment_score ?? 0.5} label={report.sentiment_label ?? 'Neutral'} />
            <span className="sentiment-score">{Math.round((report.sentiment_score ?? 0.5) * 100)}/100</span>
          </div>
          {report.management_themes && (
            <p className="report-prose report-prose-sm">{report.management_themes}</p>
          )}
        </div>
      </div>

      {/* Bull / Bear */}
      <div className="bull-bear-grid">
        <div className="bull-card glass-card">
          <div className="section-label bull-label">
            <TrendingUp size={12} /> Bull Case
          </div>
          <ul className="case-list">
            {(report.bull_case ?? []).map((pt, i) => (
              <li key={i} className="case-item case-item-bull">+ {pt}</li>
            ))}
          </ul>
        </div>
        <div className="bear-card glass-card">
          <div className="section-label bear-label">
            <TrendingDown size={12} /> Bear Case
          </div>
          <ul className="case-list">
            {(report.bear_case ?? []).map((pt, i) => (
              <li key={i} className="case-item case-item-bear">− {pt}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Verdict */}
      {report.verdict && (
        <div className="verdict-box glass-card">
          <div className="section-label">
            <CheckCircle size={12} /> Verdict
          </div>
          <p className="verdict-text">{report.verdict}</p>
        </div>
      )}
    </div>
  )
}
