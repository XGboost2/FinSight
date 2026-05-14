import { TrendingUp, Sun, Moon, FileText, Activity, Shield, BarChart2 } from 'lucide-react'
import CompanySearch from './CompanySearch'

const FEATURES = [
  {
    icon: FileText,
    title: '10-K Deep Dive',
    desc: 'Automated SEC EDGAR ingestion with XBRL financials and section-aware RAG retrieval',
  },
  {
    icon: Activity,
    title: 'FinBERT Sentiment',
    desc: 'NLP-powered tone analysis on MD&A sections with year-over-year comparison',
  },
  {
    icon: Shield,
    title: 'Risk Intelligence',
    desc: 'Item 1A risk factor extraction, 8-K event tracking, and YoY diff analysis',
  },
  {
    icon: BarChart2,
    title: 'Technical Analysis',
    desc: 'RSI, MACD, Bollinger Bands, and LLM-generated verdict on price action',
  },
]

export default function LandingPage({ onSelect, theme, onToggleTheme }) {
  return (
    <div className="landing">
      <header className="landing-header">
        <div className="brand">
          <TrendingUp size={20} />
          <span>FinSight</span>
        </div>
        <button
          className="btn-icon"
          onClick={onToggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
        </button>
      </header>

      <div className="landing-body">
        <div className="landing-icon">
          <TrendingUp size={28} />
        </div>

        <h1 className="landing-heading">What equity would you like to analyze?</h1>
        <p className="landing-sub">SEC EDGAR filings · YoY risk analysis · AI-powered insights</p>

        <div className="landing-search-wrap">
          <CompanySearch
            onSelect={onSelect}
            placeholder="Enter a ticker or company name (AAPL, Apple…)"
            variant="landing"
          />
        </div>

        <p className="landing-disclaimer">Not investment advice. For informational purposes only.</p>

        <div className="landing-features">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="feature-card glass-card">
              <div className="feature-icon">
                <Icon size={20} />
              </div>
              <h3 className="feature-title">{title}</h3>
              <p className="feature-desc">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      <footer className="landing-footer">
        <span>AI-powered · SEC EDGAR filings · FinBERT sentiment · Real-time RAG</span>
      </footer>
    </div>
  )
}
