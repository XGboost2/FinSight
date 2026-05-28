import { useEffect, useState } from 'react'
import { Shield, AlertTriangle, Calendar, Tag, Loader, Plus, Minus, ArrowRight, RefreshCw } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL ?? ''

const EVENT_COLORS = {
  earnings:    'event-earnings',
  legal:       'event-legal',
  acquisition: 'event-earnings',   // reuse green
  guidance:    'event-guidance',
  leadership:  'event-leadership',
  other:       'event-other',
}

function RiskGauge({ score }) {
  const pct  = Math.round((score ?? 0) * 100)
  const cls  = score < 0.35 ? 'gauge-low' : score < 0.6 ? 'gauge-moderate' : 'gauge-high'
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

function DiffSection({ section }) {
  if (!section) return null
  return (
    <div className="diff-view">
      <div className="diff-years glass-card">
        <span className="diff-year prior">{section.prior_year}</span>
        <ArrowRight size={13} className="diff-arrow" />
        <span className="diff-year current">{section.current_year}</span>
        <span className="diff-section-name">{section.section}</span>
      </div>
      {section.summary && (
        <div className="report-section glass-card">
          <div className="section-label">What Changed</div>
          <p className="report-prose">{section.summary}</p>
        </div>
      )}
      <div className="diff-grid">
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-new"><Plus size={12} /> New This Year <span className="diff-count">{section.new?.length ?? 0}</span></div>
          {section.new?.length > 0 ? section.new.map((p, i) => <div key={i} className="diff-item diff-item-new">{p}</div>) : <div className="diff-empty">None</div>}
        </div>
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-changed"><RefreshCw size={12} /> Changed <span className="diff-count">{section.changed?.length ?? 0}</span></div>
          {section.changed?.length > 0 ? section.changed.map((c, i) => (
            <div key={i} className="diff-item diff-item-changed">
              <div className="diff-before">{c.prior}</div>
              <div className="diff-arrow-row"><ArrowRight size={10} /></div>
              <div className="diff-after">{c.current}</div>
            </div>
          )) : <div className="diff-empty">None</div>}
        </div>
        <div className="diff-col glass-card">
          <div className="diff-col-header diff-header-removed"><Minus size={12} /> Removed <span className="diff-count">{section.removed?.length ?? 0}</span></div>
          {section.removed?.length > 0 ? section.removed.map((p, i) => <div key={i} className="diff-item diff-item-removed">{p}</div>) : <div className="diff-empty">None</div>}
        </div>
      </div>
      <div className="diff-unchanged">{section.unchanged_count} paragraph{section.unchanged_count !== 1 ? 's' : ''} unchanged</div>
    </div>
  )
}

export default function RiskTab({ ticker, onStatusChange }) {
  const [report,  setReport]  = useState(null)
  const [diff,    setDiff]    = useState(null)
  const [events,  setEvents]  = useState([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    Promise.all([
      axios.get(`${API_URL}/api/companies/${ticker}/report`),
      axios.get(`${API_URL}/api/companies/${ticker}/diff`).catch(() => ({ data: null })),
      axios.get(`${API_URL}/api/companies/${ticker}/events`).catch(() => ({ data: { events: [] } })),
    ]).then(([r, d, e]) => {
      setReport(r.data)
      setDiff(d.data)
      setEvents(e.data?.events ?? [])
      onStatusChange?.('done')
    }).catch(e => {
      setError(e.response?.data?.detail || 'Failed to load risk data.')
      onStatusChange?.('error')
    }).finally(() => setLoading(false))
  }, [ticker])

  if (loading) return (
    <div className="tab-view">
      <div className="report-loading glass-card"><Loader size={14} className="spin" /><span>Loading risk analysis…</span></div>
    </div>
  )

  if (error) return (
    <div className="tab-view">
      <div className="report-error glass-card"><AlertTriangle size={14} /><span>{error}</span></div>
    </div>
  )

  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Shield size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Risk Analyst</span>
            <span className="tab-agent-source">Item 1A · 8-K Events · YoY Diff</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">Live</span>
      </div>

      {report && (
        <div className="tab-row-2col">
          <div className="tab-section glass-card">
            <div className="section-label">Risk Score</div>
            <RiskGauge score={report.risk_score ?? 0} />
          </div>
          <div className="tab-section glass-card">
            <div className="section-label"><AlertTriangle size={12} /> Top Risk Factors</div>
            <ul className="risk-list-report">
              {(report.risk_factors ?? []).map((r, i) => (
                <li key={i} className="risk-item-report">{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {events.length > 0 && (
        <div className="tab-section glass-card">
          <div className="section-label"><Calendar size={12} /> Recent 8-K Events</div>
          <div className="events-list">
            {events.slice().reverse().map((ev, i) => (
              <div key={i} className="event-row">
                <span className="event-date">{ev.date}</span>
                <span className={`event-tag ${EVENT_COLORS[ev.event_type] || 'event-other'}`}>
                  <Tag size={10} /> {ev.event_type}
                </span>
                <p className="event-summary">{ev.summary}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {diff?.item_1a && (
        <div className="tab-section glass-card">
          <div className="section-label">Risk Factor Changes (YoY)</div>
          <DiffSection section={diff.item_1a} />
        </div>
      )}

      {!report && !loading && (
        <div className="tab-placeholder-note">Run analysis on the Fundamentals tab first to load risk data.</div>
      )}
    </div>
  )
}
