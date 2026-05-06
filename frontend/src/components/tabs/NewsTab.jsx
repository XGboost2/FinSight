import { useEffect } from 'react'
import { Newspaper, TrendingUp, TrendingDown, Minus, ExternalLink, Clock } from 'lucide-react'

const MOCK_HEADLINES = [
  { sentiment: 'positive', tag: 'Earnings',     headline: 'Q3 revenue beats estimates; guidance raised for FY2025' },
  { sentiment: 'neutral',  tag: 'Regulatory',   headline: 'EU antitrust review extended by 90 days pending further investigation' },
  { sentiment: 'negative', tag: 'Supply Chain', headline: 'Component shortage may impact gross margins in upcoming quarter' },
  { sentiment: 'positive', tag: 'Product',      headline: 'New product line receives strong pre-order numbers ahead of launch' },
  { sentiment: 'neutral',  tag: 'Leadership',   headline: 'CFO transition announced; incoming executive joins from Goldman Sachs' },
]

const SENTIMENT_ICON = {
  positive: <TrendingUp  size={13} className="news-sent-pos" />,
  negative: <TrendingDown size={13} className="news-sent-neg" />,
  neutral:  <Minus       size={13} className="news-sent-neu" />,
}

export default function NewsTab({ ticker, onStatusChange }) {
  useEffect(() => { onStatusChange?.('done') }, [])
  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Newspaper size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">News Analyst</span>
            <span className="tab-agent-source">Company news feed · Last 7 days</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-pending">Backend pending</span>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">Overall News Sentiment</div>
        <div className="news-sentiment-summary">
          <div className="news-sent-pill news-sent-pos-pill"><TrendingUp size={14} /> <span>Positive</span> <strong>3</strong></div>
          <div className="news-sent-pill news-sent-neu-pill"><Minus size={14} /> <span>Neutral</span> <strong>1</strong></div>
          <div className="news-sent-pill news-sent-neg-pill"><TrendingDown size={14} /> <span>Negative</span> <strong>1</strong></div>
        </div>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">Recent Headlines</div>
        <div className="news-list">
          {MOCK_HEADLINES.map((item, i) => (
            <div key={i} className="news-item">
              <div className="news-item-top">
                {SENTIMENT_ICON[item.sentiment]}
                <span className={`news-tag news-tag-${item.sentiment}`}>{item.tag}</span>
                <span className="news-time"><Clock size={11} /> 2h ago</span>
              </div>
              <p className="news-headline">{item.headline}</p>
              <div className="news-item-footer">
                <span className="news-source">Placeholder</span>
                <ExternalLink size={11} className="news-link-icon" />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="tab-placeholder-note">
        Live news data will be connected in a future update.
      </div>
    </div>
  )
}
