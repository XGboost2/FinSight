import { useEffect, useRef } from 'react'

export default function StockChart({ ticker }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!ticker || !containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''

    const theme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'

    const widgetDiv = document.createElement('div')
    widgetDiv.className = 'tradingview-widget-container__widget'
    container.appendChild(widgetDiv)

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js'
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = JSON.stringify({
      symbols:          [[ticker, `${ticker}|1M`]],
      chartOnly:        false,
      width:            '100%',
      height:           '100%',
      locale:           'en',
      colorTheme:       theme,
      isTransparent:    true,
      autosize:         true,
      showVolume:       false,
      showMA:           false,
      hideDateRanges:   false,
      hideMarketStatus: false,
      hideSymbolLogo:   true,
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
  }, [ticker])

  // Reapply theme when toggled
  useEffect(() => {
    const observer = new MutationObserver(() => {
      if (containerRef.current) {
        const ticker_ = containerRef.current.dataset.ticker
        if (ticker_) containerRef.current.dispatchEvent(new Event('themechange'))
      }
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={containerRef}
      className="tv-symbol-overview"
      data-ticker={ticker}
    />
  )
}
