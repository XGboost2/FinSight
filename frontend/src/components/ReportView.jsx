import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  FileBarChart, Loader, RefreshCw, TrendingUp, TrendingDown,
  AlertTriangle, CheckCircle, Shield, Activity,
} from 'lucide-react'
import { ReportSkeleton } from './Skeleton'
import CitationPanel from './CitationPanel'

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
  const pct   = Math.round((score ?? 0) * 100)
  const cls   = score < 0.35 ? 'gauge-low' : score < 0.6 ? 'gauge-moderate' : 'gauge-high'
  const label = score < 0.35 ? 'Low' : score < 0.6 ? 'Moderate' : 'High'
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

export default function ReportView({ ticker, compact = false, ingesting = false, onStatusChange }) {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)

  const fetchReport = async (refresh = false) => {
    if (!ticker || ingesting) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    try {
      const { data } = await axios.get(
        `${API_URL}/api/companies/${ticker}/analysis${refresh ? '?refresh=true' : ''}`
      )
      setReport(data)
      onStatusChange?.('done')
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to generate report.')
      onStatusChange?.('error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchReport() }, [ticker, ingesting])

  if (!ticker) return null

  if (ingesting || loading) return <ReportSkeleton />

  if (error) return (
    <div className="report-error glass-card" role="alert">
      <AlertTriangle size={14} />
      <span>{error}</span>
      <button className="btn-refresh" onClick={() => fetchReport()} style={{ marginLeft: 'auto' }}>
        <RefreshCw size={12} /> Retry
      </button>
    </div>
  )

  if (!report) return null
  if (report.error) return (
    <div className="report-error glass-card">
      <AlertTriangle size={14} />
      <span>Report error: {report.error}</span>
    </div>
  )

  const riskScore = report.risk_score ?? 0
  const sentScore = report.sentiment_score ?? 0.5

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

      {/* Detailed Findings Table */}
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

      {/* Financial Trend Narrative */}
      {report.trend_narrative && !compact && (
        <div className="report-section glass-card">
          <div className="section-label">Financial Trend Analysis</div>
          <p className="report-prose">{report.trend_narrative}</p>
        </div>
      )}

      {/* Risk Score + Sentiment — side by side */}
      {!compact && (
        <div className="tab-row-2col">
          <div className="tab-section glass-card">
            <div className="section-label"><Shield size={12} /> Risk Score</div>
            <RiskGauge score={riskScore} />
          </div>
          <div className="tab-section glass-card">
            <div className="section-label"><Activity size={12} /> MD&A Sentiment</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.35rem' }}>
              <SentimentBadge score={sentScore} label={report.sentiment_label ?? 'Neutral'} />
              <span className="report-generated">{Math.round(sentScore * 100)}/100</span>
            </div>
          </div>
        </div>
      )}

      {/* Top Risk Factors */}
      {report.risk_factors?.length > 0 && !compact && (
        <div className="report-section glass-card">
          <div className="section-label"><AlertTriangle size={12} /> Top Risk Factors</div>
          <ul className="risk-list-report">
            {report.risk_factors.map((r, i) => (
              <li key={i} className="risk-item-report">{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Management Themes */}
      {report.management_themes && !compact && (
        <div className="report-section glass-card">
          <div className="section-label">Management Themes</div>
          <p className="report-prose">{report.management_themes}</p>
        </div>
      )}

      {/* Verdict */}
      {report.verdict && (() => {
        const isPos = riskScore < 0.35 && sentScore >= 0.55
        const isNeg = riskScore > 0.6 || sentScore < 0.4
        const signal = isPos ? 'positive' : isNeg ? 'negative' : 'neutral'
        return (
          <div className={`verdict-box glass-card verdict-${signal}`}>
            <div className="verdict-header">
              <div className="section-label">
                <CheckCircle size={12} /> Verdict
              </div>
              <div className={`verdict-signal verdict-signal-${signal}`}>
                {isPos
                  ? <><TrendingUp  size={14} /> Positive outlook</>
                  : isNeg
                  ? <><TrendingDown size={14} /> Negative outlook</>
                  : <><span style={{ fontSize: '1rem', lineHeight: 1 }}>—</span> Neutral</>
                }
              </div>
            </div>
            <p className="verdict-text">{report.verdict}</p>
          </div>
        )
      })()}

      {!compact && <CitationPanel citations={report.citations} />}
    </div>
  )
}
