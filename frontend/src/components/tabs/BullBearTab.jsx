import { useEffect, useState } from 'react'
import { Scale, TrendingUp, TrendingDown, Loader, AlertTriangle, MessageSquare, Award, Target, Shield, Zap } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLE_STYLES = {
  Bull: { cls: 'debate-bull-msg',  icon: <TrendingUp  size={13} />, label: 'Bull' },
  Bear: { cls: 'debate-bear-msg',  icon: <TrendingDown size={13} />, label: 'Bear' },
}

const SIGNAL_CONFIG = {
  BUY:  { cls: 'signal-buy',  icon: <TrendingUp size={16} />,   label: 'BUY'  },
  HOLD: { cls: 'signal-hold', icon: <Shield size={16} />,       label: 'HOLD' },
  SELL: { cls: 'signal-sell', icon: <TrendingDown size={16} />,  label: 'SELL' },
}

function DebateWinnerCard({ report }) {
  const winner = report.debate_winner
  const bullConf = Math.round((report.bull_confidence ?? 0.5) * 100)
  const bearConf = Math.round((report.bear_confidence ?? 0.5) * 100)

  if (!winner) return null

  const isBull = winner === 'Bull'
  const isDraw = winner === 'Draw'

  return (
    <div className={`debate-winner-card glass-card ${isDraw ? 'winner-draw' : isBull ? 'winner-bull' : 'winner-bear'}`}>
      <div className="debate-winner-header">
        <Award size={18} />
        <span className="debate-winner-title">Debate Winner</span>
        <span className={`debate-winner-badge ${isDraw ? 'badge-draw' : isBull ? 'badge-bull' : 'badge-bear'}`}>
          {isDraw ? '⚖️' : isBull ? '📈' : '📉'} {winner}
        </span>
      </div>

      <div className="confidence-bars">
        <div className="confidence-row">
          <span className="confidence-label bull-label">
            <TrendingUp size={12} /> Bull
          </span>
          <div className="confidence-track">
            <div className="confidence-fill confidence-fill-bull" style={{ width: `${bullConf}%` }} />
          </div>
          <span className="confidence-pct">{bullConf}%</span>
        </div>
        <div className="confidence-row">
          <span className="confidence-label bear-label">
            <TrendingDown size={12} /> Bear
          </span>
          <div className="confidence-track">
            <div className="confidence-fill confidence-fill-bear" style={{ width: `${bearConf}%` }} />
          </div>
          <span className="confidence-pct">{bearConf}%</span>
        </div>
      </div>

      {report.verdict && (
        <div className="debate-verdict-text">
          <Zap size={12} /> {report.verdict}
        </div>
      )}
    </div>
  )
}

function PortfolioSignalCard({ signal }) {
  if (!signal) return null

  const config = SIGNAL_CONFIG[signal.signal] || SIGNAL_CONFIG.HOLD
  const confidence = Math.round((signal.confidence ?? 0.5) * 100)

  return (
    <div className={`portfolio-signal-card glass-card ${config.cls}`}>
      <div className="portfolio-signal-header">
        <Target size={18} />
        <span className="portfolio-signal-title">Portfolio Signal</span>
      </div>

      <div className="portfolio-signal-badge-row">
        <div className={`portfolio-signal-badge ${config.cls}`}>
          {config.icon}
          <span className="portfolio-signal-text">{config.label}</span>
        </div>
        <div className="portfolio-signal-confidence">
          <span className="portfolio-confidence-value">{confidence}%</span>
          <span className="portfolio-confidence-label">confidence</span>
        </div>
        {signal.risk_reward && (
          <div className={`portfolio-risk-reward rr-${signal.risk_reward?.toLowerCase()}`}>
            {signal.risk_reward}
          </div>
        )}
      </div>

      {signal.rationale && (
        <p className="portfolio-rationale">{signal.rationale}</p>
      )}

      {signal.key_factors?.length > 0 && (
        <div className="portfolio-factors">
          {signal.key_factors.map((f, i) => (
            <span key={i} className="portfolio-factor-chip">{f}</span>
          ))}
        </div>
      )}
    </div>
  )
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
            <span className="tab-agent-source">Pydantic AI debate agents · grounded in 10-K</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">Live</span>
      </div>

      {report && (
        <>
          <DebateWinnerCard report={report} />
          <PortfolioSignalCard signal={report.portfolio_signal} />

          <div className="debate-grid">
            <div className="tab-section glass-card debate-bull">
              <div className="section-label bull-label">
                <TrendingUp size={13} /> Bull Case
                {report.bull_confidence != null && (
                  <span className="case-confidence">{Math.round(report.bull_confidence * 100)}%</span>
                )}
              </div>
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
              <div className="section-label bear-label">
                <TrendingDown size={13} /> Bear Case
                {report.bear_confidence != null && (
                  <span className="case-confidence">{Math.round(report.bear_confidence * 100)}%</span>
                )}
              </div>
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
