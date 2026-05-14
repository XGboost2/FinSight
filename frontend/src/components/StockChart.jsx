import { useEffect, useRef, useState } from 'react'

const TICKER_RE = /^[A-Z0-9.\-]{1,10}$/

function sanitizeTicker(t) {
  const upper = (t || '').toUpperCase().replace(/[^A-Z0-9.\-]/g, '')
  return TICKER_RE.test(upper) ? upper : null
}

function getTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}

export default function StockChart({ ticker }) {
  const containerRef = useRef(null)
  const [colorTheme, setColorTheme] = useState(getTheme)

  // Track theme changes
  useEffect(() => {
    const observer = new MutationObserver(() => setColorTheme(getTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  // Rebuild widget when ticker or theme changes
  useEffect(() => {
    const safeTicker = sanitizeTicker(ticker)
    if (!safeTicker || !containerRef.current) return
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
      symbols:          [[safeTicker, `${safeTicker}|1M`]],
      chartOnly:        false,
      width:            '100%',
      height:           '100%',
      locale:           'en',
      colorTheme,
      isTransparent:    true,
      autosize:         true,
      showVolume:       false,
      showMA:           false,
      hideDateRanges:   false,
      hideMarketStatus: false,
      hideSymbolLogo:   false,
      scalePosition:    'right',
      scaleMode:        'Normal',
      fontFamily:       'Inter, system-ui, sans-serif',
      fontSize:         '10',
      headerFontSize:   'medium',
      noTimeScale:      false,
      valuesTracking:   '1',
      changeMode:       'price-and-percent',
      chartType:        'area',
      lineWidth:        2,
      lineType:         0,
      dateRanges:       ['1d|1', '1m|30', '3m|60', '12m|1D', '60m|1W', 'all|1M'],
      upColor:          '#22ab94',
      downColor:        '#f7525f',
      borderUpColor:    '#22ab94',
      borderDownColor:  '#f7525f',
    })
    container.appendChild(script)

    return () => { container.innerHTML = '' }
  }, [ticker, colorTheme])

  return <div ref={containerRef} className="tv-symbol-overview" />
}
