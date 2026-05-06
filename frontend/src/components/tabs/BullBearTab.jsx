import { useEffect, useState } from 'react'
import { Scale, TrendingUp, TrendingDown, Loader, AlertTriangle, MessageSquare } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLE_STYLES = {
  Bull: { cls: 'debate-bull-msg',  icon: <TrendingUp  size={13} />, label: 'Bull' },
  Bear: { cls: 'debate-bear-msg',  icon: <TrendingDown size={13} />, label: 'Bear' },
}

export default function BullBearTab({ ticker, onStatusChange }) {
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
      .catch(e => { setError(e.response?.data?.detail || 'Failed to load analysis.'); onStatusChange?.('error') })
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading) return (
    <div className="tab-view">
      <div className="report-loading glass-card"><Loader size={14} className="spin" /><span>Loading debate…</span></div>
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
          <Scale size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Bull vs Bear</span>
            <span className="tab-agent-source">LLM-simulated debate · grounded in 10-K</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">Live</span>
      </div>

      {report && (
        <>
          <div className="debate-grid">
            <div className="tab-section glass-card debate-bull">
              <div className="section-label bull-label"><TrendingUp size={13} /> Bull Case</div>
              <ul className="case-list">
                {(report.bull_case ?? []).map((pt, i) => (
                  <li key={i} className="case-item case-item-bull debate-case-item">
                    <span className="debate-num">{i + 1}</span>
                    <span>{pt}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="tab-section glass-card debate-bear">
              <div className="section-label bear-label"><TrendingDown size={13} /> Bear Case</div>
              <ul className="case-list">
                {(report.bear_case ?? []).map((pt, i) => (
                  <li key={i} className="case-item case-item-bear debate-case-item">
                    <span className="debate-num">{i + 1}</span>
                    <span>{pt}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {report.debate_transcript?.length > 0 && (
            <div className="tab-section glass-card">
              <div className="section-label">
                <MessageSquare size={12} /> Debate Transcript
              </div>
              <div className="debate-transcript">
                {report.debate_transcript.map((turn, i) => {
                  const style = ROLE_STYLES[turn.role] || ROLE_STYLES.Bull
                  return (
                    <div key={i} className={`debate-turn ${style.cls}`}>
                      <div className="debate-turn-role">
                        {style.icon} {style.label}
                      </div>
                      <p className="debate-turn-text">{turn.argument}</p>
                    </div>
                  )
                })}
              </div>
              <p className="tab-placeholder-note" style={{ marginTop: '0.75rem' }}>
                Feature 3c: CrewAI Bull + Bear researcher agents will replace this with multi-turn reasoning and filing tool access.
              </p>
            </div>
          )}
        </>
      )}

      {!report && !loading && (
        <div className="tab-placeholder-note">Run analysis on the Fundamentals tab first.</div>
      )}
    </div>
  )
}
