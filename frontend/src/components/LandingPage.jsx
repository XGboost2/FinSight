import { TrendingUp, Sun, Moon } from 'lucide-react'
import CompanySearch from './CompanySearch'

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
          title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
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
      </div>

      <footer className="landing-footer">
        <span>AI-powered · SEC EDGAR filings · FinBERT sentiment · Real-time RAG</span>
      </footer>
    </div>
  )
}
