import { useEffect, useRef } from 'react'
import { Loader, ArrowLeft } from 'lucide-react'
import ReportView from './ReportView'

function TradingViewChart({ ticker }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!ticker || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const widgetDiv = document.createElement('div')
    widgetDiv.id = `tv_cmp_${ticker}_${Date.now()}`
    widgetDiv.style.height = '100%'
    container.appendChild(widgetDiv)

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/tv.js'
    script.async = true
    script.onload = () => {
      if (!window.TradingView) return
      new window.TradingView.widget({
        autosize: true,
        symbol: ticker,
        interval: 'D',
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0d111c',
        enable_publishing: false,
        hide_side_toolbar: true,
        allow_symbol_change: false,
        container_id: widgetDiv.id,
        backgroundColor: 'rgba(8, 13, 26, 1)',
        gridColor: 'rgba(255, 255, 255, 0.04)',
      })
    }
    container.appendChild(script)

    return () => { container.innerHTML = '' }
  }, [ticker])

  return <div ref={containerRef} className="tv-chart-container" />
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

export default function CompareView({ comparison, loading, error, onBack }) {
  if (loading) {
    return (
      <div className="compare-loading">
        <Loader size={20} className="spin" />
        <span>Fetching filings, extracting metrics, generating analysis…</span>
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
        <button className="btn-back" onClick={onBack}>
          <ArrowLeft size={14} /> Back
        </button>
        <span className="compare-title">
          <strong>{ticker1}</strong> vs <strong>{ticker2}</strong>
        </span>
      </div>

      <div className="compare-charts">
        <div className="compare-chart-card glass-card">
          <div className="compare-chart-label">{ticker1}</div>
          <TradingViewChart ticker={ticker1} />
        </div>
        <div className="compare-chart-card glass-card">
          <div className="compare-chart-label">{ticker2}</div>
          <TradingViewChart ticker={ticker2} />
        </div>
      </div>

      <div className="compare-body">
        <div className="compare-bars glass-card">
          <div className="section-label">Financial Metrics</div>
          <BarRow
            label="Revenue"
            val1={metrics1.revenue_latest_year}
            val2={metrics2.revenue_latest_year}
            t1={ticker1} t2={ticker2}
          />
          <BarRow
            label="Net Income"
            val1={metrics1.net_income_latest_year}
            val2={metrics2.net_income_latest_year}
            t1={ticker1} t2={ticker2}
          />
          <BarRow
            label="Gross Margin"
            val1={metrics1.gross_margin_pct}
            val2={metrics2.gross_margin_pct}
            t1={ticker1} t2={ticker2}
          />

          {trends1.length > 0 && (
            <>
              <div className="bar-trend-divider">Revenue by Year</div>
              {trends1.map(d1 => {
                const d2 = trends2.find(d => d.year === d1.year)
                return (
                  <BarRow
                    key={d1.year}
                    label={d1.year}
                    val1={d1.value}
                    val2={d2?.value ?? null}
                    t1={ticker1}
                    t2={ticker2}
                  />
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
                    {pros.map((p, i) => (
                      <div key={i} className="pro-item">+ {p}</div>
                    ))}
                  </div>
                )}
                {cons.length > 0 && (
                  <div className="cons-list">
                    {cons.map((c, i) => (
                      <div key={i} className="con-item">- {c}</div>
                    ))}
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
