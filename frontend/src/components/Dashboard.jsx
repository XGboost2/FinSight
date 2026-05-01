import { useEffect, useRef } from 'react'
import { Loader, TrendingUp, TrendingDown, AlertTriangle, BarChart2 } from 'lucide-react'

function TradingViewChart({ ticker }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!ticker || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const widgetDiv = document.createElement('div')
    widgetDiv.id = `tv_${ticker}_${Date.now()}`
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

function MetricCard({ label, value, sub, positive }) {
  const color = positive === true ? 'var(--green)' : positive === false ? 'var(--red)' : 'var(--text)'
  return (
    <div className="metric-card glass-card">
      <span className="metric-label">{label}</span>
      <span className="metric-value" style={{ color }}>{value ?? '—'}</span>
      {sub && <span className="metric-sub">{sub}</span>}
    </div>
  )
}

function isPositive(val) {
  if (!val) return undefined
  return val.startsWith('+') ? true : val.startsWith('-') ? false : undefined
}

export default function Dashboard({ company, dashboard, loading, error }) {
  if (!company) return null

  const { ticker, name } = company

  return (
    <div className="dashboard">
      <div className="dashboard-header glass-card">
        <div className="dashboard-title">
          <span className="dashboard-ticker">{ticker}</span>
          <span className="dashboard-name">{name}</span>
        </div>
        {loading && (
          <div className="dashboard-loading">
            <Loader size={14} className="spin" />
            <span>Fetching &amp; analysing 10-K…</span>
          </div>
        )}
        {error && <div className="dashboard-error">{error}</div>}
      </div>

      <div className="dashboard-chart glass-card">
        <TradingViewChart ticker={ticker} />
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
            <MetricCard label="Revenue" value={dashboard.revenue_latest_year} />
            <MetricCard
              label="Net Income"
              value={dashboard.net_income_latest_year}
            />
            <MetricCard label="Gross Margin" value={dashboard.gross_margin_pct} />
            <MetricCard
              label="YoY Growth"
              value={dashboard.revenue_yoy_change}
              positive={isPositive(dashboard.revenue_yoy_change)}
            />
          </div>

          <div className="sections-grid">
            {dashboard.primary_revenue_segments?.length > 0 && (
              <div className="section-card glass-card">
                <div className="section-label">
                  <BarChart2 size={13} />
                  Revenue Segments
                </div>
                <ul className="segment-list">
                  {dashboard.primary_revenue_segments.map((s, i) => (
                    <li key={i} className="segment-item">
                      <span className="segment-dot" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {dashboard.top_3_risk_factors?.length > 0 && (
              <div className="section-card glass-card">
                <div className="section-label">
                  <AlertTriangle size={13} />
                  Top Risk Factors
                </div>
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
