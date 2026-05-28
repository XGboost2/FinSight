import { useEffect, useState } from 'react'
import { Newspaper, TrendingUp, TrendingDown, Minus, ExternalLink, Clock, Loader, AlertTriangle } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL ?? ''

const SENTIMENT_ICON = {
  positive: <TrendingUp  size={13} className="news-sent-pos" />,
  negative: <TrendingDown size={13} className="news-sent-neg" />,
  neutral:  <Minus       size={13} className="news-sent-neu" />,
}

function timeAgo(isoString) {
  if (!isoString) return ''
  const diff = Math.floor((Date.now() - new Date(isoString)) / 1000)
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export default function NewsTab({ ticker, onStatusChange }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    onStatusChange?.('loading')
    axios.get(`${API_URL}/api/companies/${ticker}/news`)
      .then(r => { setData(r.data); onStatusChange?.('done') })
      .catch(e => { setError(e.response?.data?.detail || 'Failed to load news.'); onStatusChange?.('error') })
      .finally(() => setLoading(false))
  }, [ticker])

  if (loading) return (
    <div className="tab-view">
      <div className="report-loading glass-card"><Loader size={14} className="spin" /><span>Fetching latest news…</span></div>
    </div>
  )
  if (error) return (
    <div className="tab-view">
      <div className="report-error glass-card"><AlertTriangle size={14} /><span>{error}</span></div>
    </div>
  )

  const items   = data?.items ?? []
  const counts  = data?.sentiment_counts ?? { positive: 0, negative: 0, neutral: 0 }
  const isEmpty = items.length === 0

  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Newspaper size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">News Analyst</span>
            <span className="tab-agent-source">Finnhub · FinBERT scored · Last 7 days</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-live">Live</span>
      </div>

      {data && !isEmpty && (
        <div className="tab-section glass-card">
          <div className="section-label">Overall News Sentiment</div>
          <div className="news-sentiment-summary">
            <div className="news-sent-pill news-sent-pos-pill"><TrendingUp size={14} /> <span>Positive</span> <strong>{counts.positive}</strong></div>
            <div className="news-sent-pill news-sent-neu-pill"><Minus size={14} />      <span>Neutral</span>  <strong>{counts.neutral}</strong></div>
            <div className="news-sent-pill news-sent-neg-pill"><TrendingDown size={14} /><span>Negative</span> <strong>{counts.negative}</strong></div>
          </div>
          {data.summary && <p className="report-prose" style={{ marginTop: '0.75rem' }}>{data.summary}</p>}
        </div>
      )}

      {!isEmpty ? (
        <div className="tab-section glass-card">
          <div className="section-label">Recent Headlines</div>
          <div className="news-list">
            {items.map((item, i) => (
              <div key={i} className="news-item">
                <div className="news-item-top">
                  {SENTIMENT_ICON[item.sentiment] ?? SENTIMENT_ICON.neutral}
                  <span className={`news-tag news-tag-${item.sentiment}`}>{item.sentiment}</span>
                  {item.published_at && (
                    <span className="news-time"><Clock size={11} /> {timeAgo(item.published_at)}</span>
                  )}
                </div>
                <p className="news-headline">{item.headline}</p>
                <div className="news-item-footer">
                  <span className="news-source">{item.source}</span>
                  {item.url && (
                    <a href={item.url} target="_blank" rel="noopener noreferrer" className="news-link">
                      <ExternalLink size={11} className="news-link-icon" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : data ? (
        <div className="tab-placeholder-note">No news found for {ticker} in the last 7 days.</div>
      ) : null}

      {!data && !loading && (
        <div className="tab-placeholder-note">Run analysis on the Fundamentals tab first.</div>
      )}
    </div>
  )
}
