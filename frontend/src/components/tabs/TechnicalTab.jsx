import { useEffect } from 'react'
import { LineChart, TrendingUp, TrendingDown, Minus } from 'lucide-react'

const INDICATORS = [
  { name: 'RSI (14)',        value: '58.4',   signal: 'neutral',  note: 'Neutral territory — neither overbought nor oversold' },
  { name: 'MACD',           value: '+0.82',   signal: 'positive', note: 'Bullish crossover — momentum turning upward' },
  { name: '50-day MA',      value: '$213.40', signal: 'positive', note: 'Price trading above 50-day MA — short-term uptrend' },
  { name: '200-day MA',     value: '$195.80', signal: 'positive', note: 'Price above 200-day MA — long-term trend intact' },
  { name: 'Volume (20d avg)', value: '61.2M',  signal: 'neutral',  note: 'Volume in line with 20-day average — no unusual activity' },
  { name: 'Bollinger Bands', value: 'Mid',    signal: 'neutral',  note: 'Price near midband — consolidation phase' },
]

const SIGNAL_ICON = {
  positive: <TrendingUp  size={13} className="tech-sig-pos" />,
  negative: <TrendingDown size={13} className="tech-sig-neg" />,
  neutral:  <Minus       size={13} className="tech-sig-neu" />,
}

const SIGNAL_CLASS = {
  positive: 'tech-badge-pos',
  negative: 'tech-badge-neg',
  neutral:  'tech-badge-neu',
}

export default function TechnicalTab({ ticker, onStatusChange }) {
  useEffect(() => { onStatusChange?.('done') }, [])
  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <LineChart size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Technical Analyst</span>
            <span className="tab-agent-source">Alpha Vantage · RSI · MACD · Moving Averages</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-pending">Backend pending</span>
      </div>

      <div className="tab-row-2col">
        <div className="tab-section glass-card">
          <div className="section-label">Overall Technical Signal</div>
          <div className="tech-overall">
            <TrendingUp size={28} className="tech-overall-icon tech-overall-pos" />
            <div>
              <span className="tech-overall-label">Moderately Bullish</span>
              <p className="report-prose report-prose-sm">4 of 6 indicators point positive. No overbought conditions.</p>
            </div>
          </div>
        </div>

        <div className="tab-section glass-card">
          <div className="section-label">Signal Summary</div>
          <div className="tech-summary-pills">
            <div className="tech-summary-pill tech-summary-pos">
              <TrendingUp size={13} /> Bullish <strong>4</strong>
            </div>
            <div className="tech-summary-pill tech-summary-neu">
              <Minus size={13} /> Neutral <strong>2</strong>
            </div>
            <div className="tech-summary-pill tech-summary-neg">
              <TrendingDown size={13} /> Bearish <strong>0</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">Indicators</div>
        <table className="tech-table">
          <thead>
            <tr>
              <th>Indicator</th>
              <th>Value</th>
              <th>Signal</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {INDICATORS.map((ind, i) => (
              <tr key={i}>
                <td className="tech-indicator-name">{ind.name}</td>
                <td className="tech-value">{ind.value}</td>
                <td>
                  <span className={`tech-badge ${SIGNAL_CLASS[ind.signal]}`}>
                    {SIGNAL_ICON[ind.signal]} {ind.signal}
                  </span>
                </td>
                <td className="tech-note">{ind.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="tab-placeholder-note">
        Live technical indicators will be fetched from Alpha Vantage (key already configured) when the Technical Analyst agent is connected.
      </div>
    </div>
  )
}
