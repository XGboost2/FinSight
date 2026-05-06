import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  FileBarChart, Loader, RefreshCw, TrendingUp, TrendingDown,
  AlertTriangle, CheckCircle,
} from 'lucide-react'

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


// ── Diff Tab ──────────────────────────────────────────────────────────

function DiffSection({ section, loading, error }) {
  if (loading) return (
    <div className="report-loading glass-card">
      <Loader size={16} className="spin" />
      <span>Computing year-over-year diff — fetching prior 10-K, this takes ~30s…</span>
    </div>
  )
  if (error) return (
    <div className="report-error glass-card">
      <AlertTriangle size={14} />
      <span>{error}</span>
    </div>
  )
  if (!section) return null

  return (
    <div className="diff-view">
      {/* Year badge */}
      <div className="diff-years glass-card">
        <span className="diff-year prior">{section.prior_year}</span>
        <ArrowRight size={14} className="diff-arrow" />
        <span className="diff-year current">{section.current_year}</span>
        <span className="diff-section-name">{section.section}</span>
      </div>

      {/* LLM summary */}
      {section.summary && (
        <div className="report-section glass-card">
          <div className="section-label">What Changed</div>
          <p className="report-prose">{section.summary}</p>
        </div>
      )}

      {/* New / Changed / Removed */}
      <div className="diff-grid">
        {/* New */}
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-new">
            <Plus size={12} /> New This Year
            <span className="diff-count">{section.new?.length ?? 0}</span>
          </div>
          {section.new?.length > 0
            ? section.new.map((item, i) => (
                <div key={i} className="diff-item diff-item-new">{item}</div>
              ))
            : <div className="diff-empty">No new additions</div>
          }
        </div>

        {/* Changed */}
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-changed">
            <RefreshCw size={12} /> Changed
            <span className="diff-count">{section.changed?.length ?? 0}</span>
          </div>
          {section.changed?.length > 0
            ? section.changed.map((item, i) => (
                <div key={i} className="diff-item diff-item-changed">
                  <div className="diff-before">{item.prior}</div>
                  <div className="diff-arrow-row"><ArrowRight size={10} /></div>
                  <div className="diff-after">{item.current}</div>
                </div>
              ))
            : <div className="diff-empty">No changes detected</div>
          }
        </div>

        {/* Removed */}
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-removed">
            <Minus size={12} /> Removed
            <span className="diff-count">{section.removed?.length ?? 0}</span>
          </div>
          {section.removed?.length > 0
            ? section.removed.map((item, i) => (
                <div key={i} className="diff-item diff-item-removed">{item}</div>
              ))
            : <div className="diff-empty">Nothing removed</div>
          }
        </div>
      </div>

      <div className="diff-unchanged">
        {section.unchanged_count} paragraph{section.unchanged_count !== 1 ? 's' : ''} unchanged
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────

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
        `${API_URL}/api/companies/${ticker}/report${refresh ? '?refresh=true' : ''}`
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

      {/* Analysis content */}
      <>

          {report.company_overview && (
            <div className="report-section glass-card">
              <div className="section-label">Company Overview</div>
              <p className="report-prose">{report.company_overview}</p>
            </div>
          )}

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

          {report.trend_narrative && !compact && (
            <div className="report-section glass-card">
              <div className="section-label">Financial Trend Analysis</div>
              <p className="report-prose">{report.trend_narrative}</p>
            </div>
          )}
      </>

      {/* Verdict — always visible */}
      {report.verdict && (() => {
        const risk = report.risk_score ?? 0.5
        const sent = report.sentiment_score ?? 0.5
        const isPos = risk < 0.35 && sent >= 0.55
        const isNeg = risk > 0.6 || sent < 0.4
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
    </div>
  )
}
