import { useState, useRef, useCallback } from 'react'
import { Search, ArrowRight } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function CompanySearch({ onSelect, placeholder = 'Search company…', disabled = false, variant = 'default' }) {
  const isLanding = variant === 'landing'
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  const search = useCallback(async (q) => {
    if (q.length < 2) { setResults([]); return }
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/companies/search?q=${encodeURIComponent(q)}`)
      const json = await res.json()
      setResults(json.results || [])
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [])

  const handleChange = (e) => {
    const val = e.target.value
    setQuery(val)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(val), 280)
  }

  const handleSelect = (company) => {
    setQuery(company.name)
    setResults([])
    onSelect(company)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && results.length > 0) handleSelect(results[0])
    if (e.key === 'Escape') setResults([])
  }

  const handleBlur = (e) => {
    if (!containerRef.current?.contains(e.relatedTarget)) setResults([])
  }

  return (
    <div className={`cs-container${isLanding ? ' cs-landing' : ''}`} ref={containerRef} onBlur={handleBlur}>
      <div className={`search-box${isLanding ? ' search-box-landing' : ''}`}>
        {!isLanding && <Search size={15} className="search-icon" />}
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="search-input"
          disabled={disabled}
          autoFocus={isLanding}
        />
        {loading && <div className="search-spinner" />}
        {isLanding && (
          <button
            className="landing-search-btn"
            onClick={() => results.length > 0 && handleSelect(results[0])}
            disabled={results.length === 0}
            title="Analyze"
          >
            <ArrowRight size={18} />
          </button>
        )}
      </div>

      {results.length > 0 && (
        <ul className={`suggestions${isLanding ? ' suggestions-landing' : ''}`}>
          {results.map(r => (
            <li
              key={r.ticker}
              className="suggestion-item"
              tabIndex={0}
              onClick={() => handleSelect(r)}
              onKeyDown={e => e.key === 'Enter' && handleSelect(r)}
            >
              <span className="sugg-sym">{r.ticker}</span>
              <span className="sugg-name">{r.name}</span>
              <span className="sugg-cik">{r.cik}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
