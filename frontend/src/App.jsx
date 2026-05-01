import { useState, useCallback, useRef } from 'react'
import axios from 'axios'
import { TrendingUp, Search } from 'lucide-react'
import StockChart from './components/StockChart'
import FilingPanel from './components/FilingPanel'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const AV_KEY = import.meta.env.VITE_ALPHA_VANTAGE_KEY || 'demo'

export default function App() {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [suggLoading, setSuggLoading] = useState(false)

  const [ticker, setTicker] = useState(null)
  const [companyName, setCompanyName] = useState('')
  const [filing, setFiling] = useState(null)
  const [filingId, setFilingId] = useState(null)
  const [fetchingFiling, setFetchingFiling] = useState(false)
  const [filingError, setFilingError] = useState(null)

  const debounceRef = useRef(null)

  const searchSuggestions = useCallback(async (kw) => {
    if (kw.length < 2) { setSuggestions([]); return }
    setSuggLoading(true)
    try {
      const res = await fetch(
        `https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords=${encodeURIComponent(kw)}&apikey=${AV_KEY}`
      )
      const json = await res.json()
      setSuggestions((json.bestMatches || []).slice(0, 6))
    } catch {
      setSuggestions([])
    } finally {
      setSuggLoading(false)
    }
  }, [])

  const handleQueryChange = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => searchSuggestions(val), 300)
  }

  const selectCompany = async (sym, name) => {
    setTicker(sym)
    setCompanyName(name)
    setQuery(name)
    setSuggestions([])
    setFiling(null)
    setFilingId(null)
    setFilingError(null)
    setFetchingFiling(true)

    try {
      const { data } = await axios.post(`${API_URL}/api/filings/fetch`, {
        ticker: sym,
        filing_type: '10-K',
      })
      if (data.success && data.filing) {
        setFiling(data.filing)
        setFilingId(data.filing.id)
      }
    } catch (e) {
      setFilingError(e.response?.data?.detail || 'Failed to fetch 10-K from SEC EDGAR.')
    } finally {
      setFetchingFiling(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && suggestions.length > 0) {
      const top = suggestions[0]
      selectCompany(top['1. symbol'], top['2. name'])
    }
    if (e.key === 'Escape') setSuggestions([])
  }

  const closeSuggestions = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setSuggestions([])
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <TrendingUp size={20} />
          <span>FinSight</span>
        </div>

        <div className="search-container" onBlur={closeSuggestions}>
          <div className="search-box">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              value={query}
              onChange={handleQueryChange}
              onKeyDown={handleKeyDown}
              placeholder="Search company (e.g. Apple Inc, Tesla…)"
              className="search-input"
            />
            {suggLoading && <div className="search-spinner" />}
          </div>

          {suggestions.length > 0 && (
            <ul className="suggestions" tabIndex={-1}>
              {suggestions.map(s => (
                <li
                  key={s['1. symbol']}
                  className="suggestion-item"
                  tabIndex={0}
                  onClick={() => selectCompany(s['1. symbol'], s['2. name'])}
                  onKeyDown={e => e.key === 'Enter' && selectCompany(s['1. symbol'], s['2. name'])}
                >
                  <span className="sugg-sym">{s['1. symbol']}</span>
                  <span className="sugg-name">{s['2. name']}</span>
                  <span className="sugg-region">{s['4. region']}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {ticker && (
          <div className="active-ticker">
            <span className="ticker-sym">{ticker}</span>
            <span className="ticker-co">{companyName}</span>
          </div>
        )}
      </header>

      <main className="layout">
        <section className="chart-col">
          <StockChart ticker={ticker} />
          {filingError && <div className="alert-error">{filingError}</div>}
        </section>
        <aside className="filing-col">
          <FilingPanel
            ticker={ticker}
            companyName={companyName}
            filingId={filingId}
            filing={filing}
            fetchingFiling={fetchingFiling}
          />
        </aside>
      </main>
    </div>
  )
}
