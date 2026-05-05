import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'

const TIMEFRAMES = ['1D', '1W', '1M', 'YTD', '1Y', '5Y']

const SERIES_OPTS = {
  upColor: '#0A7C42',
  downColor: '#CC0000',
  borderUpColor: '#0A7C42',
  borderDownColor: '#CC0000',
  wickUpColor: '#0A7C42',
  wickDownColor: '#CC0000',
}

function getChartTheme() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark'
  return dark ? {
    layout: { background: { color: '#132030' }, textColor: '#9EB0C4' },
    grid: {
      vertLines: { color: 'rgba(100,160,220,0.06)' },
      horzLines: { color: 'rgba(100,160,220,0.06)' },
    },
    rightPriceScale: { borderColor: 'rgba(100,160,220,0.14)' },
    timeScale: { borderColor: 'rgba(100,160,220,0.14)', timeVisible: false, secondsVisible: false },
  } : {
    layout: { background: { color: '#FFFFFF' }, textColor: '#4D4845' },
    grid: {
      vertLines: { color: 'rgba(51,48,46,0.05)' },
      horzLines: { color: 'rgba(51,48,46,0.05)' },
    },
    rightPriceScale: { borderColor: '#E8DDD0' },
    timeScale: { borderColor: '#E8DDD0', timeVisible: false, secondsVisible: false },
  }
}

function cutoffDate(tf) {
  const d = new Date()
  switch (tf) {
    case '1W': d.setDate(d.getDate() - 7); break
    case '1M': d.setMonth(d.getMonth() - 1); break
    case 'YTD': d.setMonth(0, 1); break
    case '1Y': d.setFullYear(d.getFullYear() - 1); break
    case '5Y': d.setFullYear(d.getFullYear() - 5); break
    default: break
  }
  return d
}

async function loadCandles(symbol, timeframe) {
  const key = import.meta.env.VITE_ALPHA_VANTAGE_KEY || 'demo'

  if (timeframe === '1D') {
    const url = `https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=${symbol}&interval=5min&outputsize=compact&apikey=${key}`
    const res = await fetch(url)
    const json = await res.json()

    if (json['Note']) throw new Error('API rate limit — free tier: 25 calls/day, 5/min')
    if (json['Information']) throw new Error('Set VITE_ALPHA_VANTAGE_KEY in .env (free at alphavantage.co)')

    const series = json['Time Series (5min)']
    if (!series) throw new Error(`No intraday data for ${symbol}`)

    const today = new Date().toISOString().slice(0, 10)
    const candles = Object.entries(series)
      .filter(([dt]) => dt.startsWith(today))
      .map(([dt, v]) => ({
        time: Math.floor(new Date(dt.replace(' ', 'T') + 'Z').getTime() / 1000),
        open: +v['1. open'], high: +v['2. high'],
        low: +v['3. low'], close: +v['4. close'],
      }))
      .sort((a, b) => a.time - b.time)

    if (!candles.length) throw new Error('No data for today — market may be closed')
    return { candles, intraday: true }
  }

  const weekly = timeframe === '5Y'
  const fn = weekly ? 'TIME_SERIES_WEEKLY' : 'TIME_SERIES_DAILY'
  const url = `https://www.alphavantage.co/query?function=${fn}&symbol=${symbol}&outputsize=full&apikey=${key}`
  const res = await fetch(url)
  const json = await res.json()

  if (json['Note']) throw new Error('API rate limit — free tier: 25 calls/day, 5/min')
  if (json['Information']) throw new Error('Set VITE_ALPHA_VANTAGE_KEY in .env (free at alphavantage.co)')

  const dataKey = weekly ? 'Weekly Time Series' : 'Time Series (Daily)'
  const series = json[dataKey]
  if (!series) throw new Error(`No data for ${symbol} — check the ticker symbol`)

  const cutoff = cutoffDate(timeframe)
  const candles = Object.entries(series)
    .filter(([date]) => new Date(date) >= cutoff)
    .map(([date, v]) => ({
      time: date,
      open: +v['1. open'], high: +v['2. high'],
      low: +v['3. low'], close: +v['4. close'],
    }))
    .sort((a, b) => (a.time < b.time ? -1 : 1))

  if (!candles.length) throw new Error('No data available for this range')
  return { candles, intraday: false }
}

export default function StockChart({ ticker }) {
  const wrapRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)
  const [activeFrame, setActiveFrame] = useState('1M')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [quote, setQuote] = useState(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return

    const chart = createChart(el, {
      ...getChartTheme(),
      crosshair: { mode: 1 },
      width: el.clientWidth,
      height: 420,
    })
    chartRef.current = chart

    // Reapply theme when user toggles day/night
    const observer = new MutationObserver(() => {
      if (chartRef.current) chartRef.current.applyOptions(getChartTheme())
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

    const ro = new ResizeObserver(() => {
      if (el && chartRef.current) {
        chartRef.current.applyOptions({ width: el.clientWidth })
      }
    })
    ro.observe(el)

    return () => {
      observer.disconnect()
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!ticker || !chartRef.current) return

    let cancelled = false
    setLoading(true)
    setError(null)
    setQuote(null)

    loadCandles(ticker, activeFrame)
      .then(({ candles, intraday }) => {
        if (cancelled || !chartRef.current) return

        chartRef.current.applyOptions({
          timeScale: { timeVisible: intraday, secondsVisible: false },
        })

        if (seriesRef.current) chartRef.current.removeSeries(seriesRef.current)
        const s = chartRef.current.addCandlestickSeries(SERIES_OPTS)
        s.setData(candles)
        seriesRef.current = s
        chartRef.current.timeScale().fitContent()

        const n = candles.length
        if (n >= 2) {
          const last = candles[n - 1]
          const prev = candles[n - 2]
          const chg = last.close - prev.close
          setQuote({ price: last.close, chg, pct: (chg / prev.close) * 100 })
        }
      })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [ticker, activeFrame])

  const isUp = !quote || quote.chg >= 0

  return (
    <div className="chart-card glass-card">
      <div className="chart-topbar">
        <div className="chart-price-row">
          {quote ? (
            <>
              <span className="price-main">${quote.price.toFixed(2)}</span>
              <span className={`price-change ${isUp ? 'pos' : 'neg'}`}>
                {isUp ? '+' : ''}{quote.chg.toFixed(2)}&nbsp;
                ({isUp ? '+' : ''}{quote.pct.toFixed(2)}%)
              </span>
            </>
          ) : (
            <span className="price-placeholder">
              {ticker ? ticker : 'Search a company above'}
            </span>
          )}
        </div>

        <div className="tf-row">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              className={`tf-btn${activeFrame === tf ? ' active' : ''}`}
              onClick={() => setActiveFrame(tf)}
              disabled={loading || !ticker}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-body">
        {!ticker && (
          <div className="chart-empty">Search for a company to load the chart</div>
        )}
        {loading && (
          <div className="chart-overlay">
            <div className="chart-spinner" />
            <span>Loading {activeFrame} data…</span>
          </div>
        )}
        {error && !loading && (
          <div className="chart-overlay error">{error}</div>
        )}
        <div ref={wrapRef} className="lw-chart" />
      </div>
    </div>
  )
}
