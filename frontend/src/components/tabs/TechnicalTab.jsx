import { useEffect, useRef, useState } from 'react'
import { LineChart, TrendingUp, TrendingDown, Minus, Loader, AlertTriangle, RefreshCw } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL ?? ''

const TICKER_RE = /^[A-Z0-9.\-]{1,10}$/

function sanitizeTicker(t) {
  const upper = (t || '').toUpperCase().replace(/[^A-Z0-9.\-]/g, '')
  return TICKER_RE.test(upper) ? upper : null
}

function getTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

const SIGNAL_CONFIG = {
  buy:     { cls: 'signal-positive', icon: <TrendingUp  size={12} />, label: 'Buy'     },
  sell:    { cls: 'signal-negative', icon: <TrendingDown size={12} />, label: 'Sell'    },
  neutral: { cls: 'signal-neutral',  icon: <Minus       size={12} />, label: 'Neutral' },
}

const OVERALL_CONFIG = {
  'Bullish':        { cls: 'tech-overall-pos', icon: <TrendingUp  size={26} /> },
  'Mildly Bullish': { cls: 'tech-overall-pos', icon: <TrendingUp  size={26} /> },
  'Bearish':        { cls: 'tech-overall-neg', icon: <TrendingDown size={26} /> },
  'Mildly Bearish': { cls: 'tech-overall-neg', icon: <TrendingDown size={26} /> },
  'Neutral':        { cls: 'tech-overall-neu', icon: <Minus       size={26} /> },
}

function TradingViewWidget({ ticker, colorTheme }) {
  const containerRef = useRef(null)

  useEffect(() => {
    const safeTicker = sanitizeTicker(ticker)
    if (!safeTicker || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const widgetDiv = document.createElement('div')
    container.appendChild(widgetDiv)

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      symbol: safeTicker, interval: '1D', width: '100%', height: 400,
      isTransparent: true, showIntervalTabs: true, locale: 'en', colorTheme,
    })
    container.appendChild(script)
    return () => { container.innerHTML = '' }
  }, [ticker, colorTheme])

  return <div ref={containerRef} />
}

export default function TechnicalTab({ ticker, onStatusChange }) {
  const [data,     setData]    = useState(null)
  const [loading,  setLoading] = useState(false)
  const [error,    setError]   = useState(null)
  const [colorTheme, setColorTheme] = useState(getTheme)

  useEffect(() => {
    const observer = new MutationObserver(() => setColorTheme(getTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  const fetchData = (refresh = false) => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    axios.get(`${API_URL}/api/companies/${ticker}/technicals${refresh ? '?refresh=true' : ''}`)
      .then(r => { setData(r.data); onStatusChange?.('done') })
      .catch(e => { setError(e.response?.data?.detail || 'Failed to load technicals.'); onStatusChange?.('error') })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [ticker])

  const overall = data?.overall_signal ?? 'Neutral'
  const overallCfg = OVERALL_CONFIG[overall] ?? OVERALL_CONFIG['Neutral']
  const counts  = data?.signal_counts ?? { buy: 0, neutral: 0, sell: 0 }

  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <LineChart size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Technical Analyst</span>
            <span className="tab-agent-source">yfinance · RSI · MACD · SMA50/200 · Bollinger Bands · Volume</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {!loading && data && (
            <button className="btn-refresh" onClick={() => fetchData(true)} title="Refresh indicators">
              <RefreshCw size={11} /> Refresh
            </button>
          )}
          <span className="tab-agent-badge badge-live">Live</span>
        </div>
      </div>

      {loading && (
        <div className="report-loading glass-card">
          <Loader size={14} className="spin" />
          <span>Computing indicators — fetching 1 year of price data…</span>
        </div>
      )}

      {error && (
        <div className="report-error glass-card">
          <AlertTriangle size={14} /><span>{error}</span>
        </div>
      )}

      {data && !loading && (
        <>
          {/* Overall signal + LLM verdict */}
          <div className="tab-row-2col">
            <div className="tab-section glass-card">
              <div className="section-label">Overall Signal</div>
              <div className="tech-overall">
                <span className={`tech-overall-icon ${overallCfg.cls}`}>{overallCfg.icon}</span>
                <div>
                  <span className="tech-overall-label">{overall}</span>
                  <p className="report-prose report-prose-sm">
                    {counts.buy} buy · {counts.neutral} neutral · {counts.sell} sell
                  </p>
                </div>
              </div>
            </div>

            <div className="tab-section glass-card">
              <div className="section-label">Signal Breakdown</div>
              <div className="tech-summary-pills">
                <div className="tech-summary-pill tech-summary-pos">
                  <TrendingUp size={12} /> Buy <strong>{counts.buy}</strong>
                </div>
                <div className="tech-summary-pill tech-summary-neu">
                  <Minus size={12} /> Neutral <strong>{counts.neutral}</strong>
                </div>
                <div className="tech-summary-pill tech-summary-neg">
                  <TrendingDown size={12} /> Sell <strong>{counts.sell}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* LLM verdict */}
          {data.verdict && (
            <div className="tab-section glass-card">
              <div className="section-label">AI Technical Verdict</div>
              <p className="report-prose">{data.verdict}</p>
            </div>
          )}

          {/* Indicator table */}
          {data.indicators?.length > 0 && (
            <div className="tab-section glass-card">
              <div className="section-label">Indicators</div>
              <table className="tech-table">
                <thead>
                  <tr>
                    <th>Indicator</th><th>Value</th><th>Signal</th><th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {data.indicators.map((ind, i) => {
                    const cfg = SIGNAL_CONFIG[ind.signal] ?? SIGNAL_CONFIG.neutral
                    return (
                      <tr key={i}>
                        <td className="tech-indicator-name">{ind.name}</td>
                        <td className="tech-value">{ind.value}</td>
                        <td>
                          <span className={`signal-badge ${cfg.cls}`}>
                            {cfg.icon} {cfg.label}
                          </span>
                        </td>
                        <td className="tech-note">{ind.note}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* TradingView technical analysis widget */}
          <div className="tab-section glass-card">
            <div className="section-label">TradingView Technical Analysis</div>
            <TradingViewWidget ticker={ticker} colorTheme={colorTheme} />
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div className="tab-placeholder-note">Select a company to run technical analysis.</div>
      )}
    </div>
  )
}
