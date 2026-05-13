import { useEffect, useRef, useState } from 'react'
import { Loader, ArrowLeft, Shield, Activity } from 'lucide-react'
import axios from 'axios'
import ReportView from './ReportView'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function getTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

function CompareOverlayChart({ ticker1, ticker2, colorTheme }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!ticker1 || !ticker2 || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const widgetDiv = document.createElement('div')
    widgetDiv.className = 'tradingview-widget-container__widget'
    container.appendChild(widgetDiv)

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      symbols:          [[ticker1, `${ticker1}|1D`]],
      compareSymbol:    { symbol: ticker2, lineColor: 'rgba(41, 98, 255, 1)', lineWidth: 2 },
      chartOnly:        false,
      width:            '100%',
      height:           440,
      locale:           'en',
      colorTheme,
      isTransparent:    true,
      autosize:         false,
      showVolume:       false,
      showMA:           false,
      hideDateRanges:   false,
      hideMarketStatus: false,
      hideSymbolLogo:   false,
      scalePosition:    'right',
      scaleMode:        'Percentage',
      fontFamily:       'Inter, system-ui, sans-serif',
      fontSize:         '10',
      noTimeScale:      false,
      valuesTracking:   '1',
      changeMode:       'price-only',
      chartType:        'line',
      lineWidth:        2,
      lineType:         0,
      dateRanges:       ['1w|15', '1m|60', '3m|60', '12m|1D', 'all|1M'],
      dateFormat:       'MMM dd, yyyy',
    })
    container.appendChild(script)

    return () => { container.innerHTML = '' }
  }, [ticker1, ticker2, colorTheme])

  return <div ref={containerRef} />
}

function parseNumber(val) {
  if (!val) return 0
  const s = val.replace(/[$B%+,\s]/g, '')
  const n = parseFloat(s)
  return isNaN(n) ? 0 : n
}

function BarRow({ label, val1, val2, t1, t2 }) {
  const n1 = parseNumber(val1)
  const n2 = parseNumber(val2)
  const max = Math.max(n1, n2, 0.001)
  const pct1 = Math.round((n1 / max) * 100)
  const pct2 = Math.round((n2 / max) * 100)

  return (
    <div className="bar-group">
      <div className="bar-metric-label">{label}</div>
      <div className="bar-row">
        <span className="bar-ticker">{t1}</span>
        <div className="bar-track">
          <div className="bar-fill bar-fill-1" style={{ width: `${pct1}%` }} />
        </div>
        <span className="bar-val">{val1 ?? '—'}</span>
      </div>
      <div className="bar-row">
        <span className="bar-ticker">{t2}</span>
        <div className="bar-track">
          <div className="bar-fill bar-fill-2" style={{ width: `${pct2}%` }} />
        </div>
        <span className="bar-val">{val2 ?? '—'}</span>
      </div>
    </div>
  )
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

function ScorePanel({ ticker, report, loading }) {
  return (
    <div className="compare-score-col">
      <div className="compare-score-ticker">{ticker}</div>
      {loading && <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}><Loader size={11} className="spin" /> Loading…</div>}
      {report && !loading && (
        <>
          <div className="compare-score-row">
            <span className="compare-score-label"><Shield size={11} /> Risk</span>
            <RiskGauge score={report.risk_score ?? 0} />
          </div>
          <div className="compare-score-row">
            <span className="compare-score-label"><Activity size={11} /> Sentiment</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <SentimentBadge score={report.sentiment_score ?? 0.5} label={report.sentiment_label ?? 'Neutral'} />
              <span className="compare-score-value">{Math.round((report.sentiment_score ?? 0.5) * 100)}/100</span>
            </div>
          </div>
          {report.verdict && (
            <p className="compare-score-verdict">{report.verdict}</p>
          )}
        </>
      )}
    </div>
  )
}

export default function CompareView({ comparison, loading, error, onBack }) {
  const [colorTheme, setColorTheme] = useState(getTheme)
  const [reports, setReports]       = useState({})
  const [reportsLoading, setReportsLoading] = useState(false)

  useEffect(() => {
    const observer = new MutationObserver(() => setColorTheme(getTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!comparison) return
    const { ticker1, ticker2 } = comparison
    setReports({})
    setReportsLoading(true)
    Promise.all([
      axios.get(`${API_URL}/api/companies/${ticker1}/analysis`).then(r => ({ ticker: ticker1, data: r.data })).catch(() => null),
      axios.get(`${API_URL}/api/companies/${ticker2}/analysis`).then(r => ({ ticker: ticker2, data: r.data })).catch(() => null),
    ]).then(results => {
      const map = {}
      results.forEach(r => { if (r) map[r.ticker] = r.data })
      setReports(map)
    }).finally(() => setReportsLoading(false))
  }, [comparison?.ticker1, comparison?.ticker2])

  if (loading) {
    return (
      <div className="compare-loading">
        <Loader size={36} className="spin compare-loading-spinner" />
        <div className="compare-loading-text">Fetching filings, extracting metrics, generating analysis…</div>
        <div className="compare-loading-sub">This may take up to 15 seconds</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="compare-error">
        <p>{error}</p>
        <button className="btn-back" onClick={onBack}>Back</button>
      </div>
    )
  }

  if (!comparison) return null

  const { ticker1, ticker2, metrics1, metrics2, analysis, trends1 = [], trends2 = [] } = comparison
  const pros1 = analysis.pros_cons?.[ticker1]?.pros ?? []
  const cons1 = analysis.pros_cons?.[ticker1]?.cons ?? []
  const pros2 = analysis.pros_cons?.[ticker2]?.pros ?? []
  const cons2 = analysis.pros_cons?.[ticker2]?.cons ?? []

  return (
    <div className="compare-view">
      <div className="compare-header glass-card">
        <div className="compare-header-left">
          <button className="btn-back" onClick={onBack}>
            <ArrowLeft size={14} /> Back
          </button>
          <span className="compare-title">
            <strong>{ticker1}</strong> vs <strong>{ticker2}</strong>
          </span>
        </div>
      </div>

      <div className="compare-chart-overlay glass-card">
        <CompareOverlayChart
          key={`${ticker1}-${ticker2}-${colorTheme}`}
          ticker1={ticker1}
          ticker2={ticker2}
          colorTheme={colorTheme}
        />
      </div>

      {/* Risk & Sentiment side-by-side */}
      <div className="compare-scores glass-card">
        <div className="section-label">Risk &amp; Sentiment</div>
        <div className="compare-scores-grid">
          <ScorePanel ticker={ticker1} report={reports[ticker1]} loading={reportsLoading} />
          <div className="compare-scores-divider" />
          <ScorePanel ticker={ticker2} report={reports[ticker2]} loading={reportsLoading} />
        </div>
      </div>

      <div className="compare-body">
        <div className="compare-bars glass-card">
          <div className="section-label">Financial Metrics</div>
          <BarRow label="Revenue"     val1={metrics1.revenue_latest_year}   val2={metrics2.revenue_latest_year}   t1={ticker1} t2={ticker2} />
          <BarRow label="Net Income"  val1={metrics1.net_income_latest_year} val2={metrics2.net_income_latest_year} t1={ticker1} t2={ticker2} />
          <BarRow label="Gross Margin" val1={metrics1.gross_margin_pct}      val2={metrics2.gross_margin_pct}      t1={ticker1} t2={ticker2} />

          {trends1.length > 0 && (
            <>
              <div className="bar-trend-divider">Revenue by Year</div>
              {trends1.map(d1 => {
                const d2 = trends2.find(d => d.year === d1.year)
                return (
                  <BarRow key={d1.year} label={d1.year} val1={d1.value} val2={d2?.value ?? null} t1={ticker1} t2={ticker2} />
                )
              })}
            </>
          )}
        </div>

        <div className="compare-analysis glass-card">
          {analysis.financial_head_to_head && (
            <div className="analysis-section">
              <div className="section-label">Financial Head-to-Head</div>
              <p className="analysis-text">{analysis.financial_head_to_head}</p>
            </div>
          )}

          <div className="pros-cons-grid">
            {[
              { ticker: ticker1, pros: pros1, cons: cons1 },
              { ticker: ticker2, pros: pros2, cons: cons2 },
            ].map(({ ticker, pros, cons }) => (
              <div key={ticker} className="pros-cons-col">
                <div className="pros-cons-ticker">{ticker}</div>
                {pros.length > 0 && (
                  <div className="pros-list">
                    {pros.map((p, i) => <div key={i} className="pro-item">+ {p}</div>)}
                  </div>
                )}
                {cons.length > 0 && (
                  <div className="cons-list">
                    {cons.map((c, i) => <div key={i} className="con-item">- {c}</div>)}
                  </div>
                )}
              </div>
            ))}
          </div>

          {analysis.strategic_positioning && (
            <div className="analysis-section">
              <div className="section-label">Strategic Positioning</div>
              <p className="analysis-text">{analysis.strategic_positioning}</p>
            </div>
          )}

          {analysis.verdict && (
            <div className="verdict-card">
              <div className="section-label">Verdict</div>
              <p className="verdict-text">{analysis.verdict}</p>
            </div>
          )}
        </div>
      </div>

      {/* Detailed reports side by side */}
      <div className="compare-reports-header">
        <div className="section-label">Detailed Analysis</div>
      </div>
      <div className="compare-reports-grid">
        <div className="compare-report-col">
          <div className="compare-report-ticker">{ticker1}</div>
          <ReportView ticker={ticker1} compact />
        </div>
        <div className="compare-report-col">
          <div className="compare-report-ticker">{ticker2}</div>
          <ReportView ticker={ticker2} compact />
        </div>
      </div>
    </div>
  )
}
