import { useEffect, useRef, useState } from 'react'
import { Loader, AlertTriangle, BarChart2, Zap, Settings } from 'lucide-react'
import StockChart from './StockChart'

function TradingViewAdvanced({ ticker }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!ticker || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const widgetId = `tv_adv_${ticker}_${Date.now()}`
    const widgetDiv = document.createElement('div')
    widgetDiv.id = widgetId
    widgetDiv.style.height = '100%'
    container.appendChild(widgetDiv)

    const mount = () => {
      if (!window.TradingView || !document.getElementById(widgetId)) return
      new window.TradingView.widget({
        autosize: true,
        symbol: ticker,
        interval: 'D',
        timezone: 'Etc/UTC',
        theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light',
        style: '1',
        locale: 'en',
        enable_publishing: false,
        hide_side_toolbar: false,
        allow_symbol_change: false,
        container_id: widgetId,
      })
    }

    if (window.TradingView) {
      mount()
    } else {
      const script = document.createElement('script')
      script.src = 'https://s3.tradingview.com/tv.js'
      script.async = true
      script.onload = mount
      document.head.appendChild(script)
    }

    return () => {
      container.innerHTML = ''
      document.querySelectorAll('[id^="tradingview_"]').forEach(el => el.remove())
    }
  }, [ticker])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}

function MetricCard({ label, value, positive }) {
  const color = positive === true ? 'var(--green)' : positive === false ? 'var(--red)' : 'var(--text)'
  return (
    <div className="metric-card glass-card">
      <span className="metric-label">{label}</span>
      <span className="metric-value" style={{ color }}>{value ?? '—'}</span>
    </div>
  )
}

function isPositive(val) {
  if (!val) return undefined
  return val.startsWith('+') ? true : val.startsWith('-') ? false : undefined
}

export default function Dashboard({ company, dashboard, loading, loadingStep, error }) {
  const [advanced, setAdvanced] = useState(false)
  if (!company) return null
  const { ticker, name } = company

  return (
    <div className="dashboard">
      <div className="dashboard-header glass-card">
        <div className="dashboard-title">
          <span className="dashboard-ticker">{ticker}</span>
          <span className="dashboard-name">{name}</span>
        </div>

        <div className="chart-toggle-group">
          <button className={`toggle-btn ${!advanced ? 'active' : ''}`} onClick={() => setAdvanced(false)}>
            <Zap size={14} /> Simple
          </button>
          <button className={`toggle-btn ${advanced ? 'active' : ''}`} onClick={() => setAdvanced(true)}>
            <Settings size={14} /> Advanced
          </button>
        </div>

        {loading && (
          <div className="dashboard-loading">
            <Loader size={14} className="spin" />
            <span>{loadingStep || 'Fetching filings…'}</span>
          </div>
        )}
        {error && <div className="dashboard-error">{error}</div>}
      </div>

      <div className="dashboard-chart glass-card">
        {advanced
          ? <TradingViewAdvanced key={ticker} ticker={ticker} />
          : <StockChart key={ticker} ticker={ticker} />
        }
      </div>

      {dashboard && (
        <>
          {dashboard.executive_summary && (
            <div className="dashboard-summary glass-card">
              <div className="section-label">Executive Summary</div>
              <p className="summary-text">{dashboard.executive_summary}</p>
            </div>
          )}

          <div className="metrics-grid">
            <MetricCard label="Revenue"      value={dashboard.revenue_latest_year} />
            <MetricCard label="Net Income"   value={dashboard.net_income_latest_year} />
            <MetricCard label="Gross Margin" value={dashboard.gross_margin_pct} />
            <MetricCard label="YoY Growth"   value={dashboard.revenue_yoy_change} positive={isPositive(dashboard.revenue_yoy_change)} />
          </div>

          <div className="sections-grid">
            {dashboard.primary_revenue_segments?.length > 0 && (
              <div className="section-card glass-card">
                <div className="section-label"><BarChart2 size={13} /> Revenue Segments</div>
                <ul className="segment-list">
                  {dashboard.primary_revenue_segments.map((s, i) => (
                    <li key={i} className="segment-item"><span className="segment-dot" />{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {dashboard.top_3_risk_factors?.length > 0 && (
              <div className="section-card glass-card">
                <div className="section-label"><AlertTriangle size={13} /> Top Risk Factors</div>
                <ol className="risk-list">
                  {dashboard.top_3_risk_factors.map((r, i) => (
                    <li key={i} className="risk-item">{r}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>

          {dashboard.management_outlook_summary && (
            <div className="dashboard-outlook glass-card">
              <div className="section-label">Management Outlook</div>
              <p className="outlook-text">"{dashboard.management_outlook_summary}"</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
