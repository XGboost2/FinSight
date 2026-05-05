import { useState, useEffect } from 'react'
import axios from 'axios'
import { TrendingUp, GitCompare, X, DollarSign, Sun, Moon } from 'lucide-react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import CompanySearch from './components/CompanySearch'
import Dashboard from './components/Dashboard'
import CompareView from './components/CompareView'
import FilingPanel from './components/FilingPanel'
import StatusDots from './components/StatusDots'
import ReportView from './components/ReportView'
import CostPanel from './components/CostPanel'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function ingestAndDashboard(ticker) {
  const { data: ingest } = await axios.post(`${API_URL}/api/companies/${ticker}/ingest`)
  const { data: dash } = await axios.get(`${API_URL}/api/companies/${ticker}/dashboard`)
  return { ingest, dashboard: dash }
}

export default function App() {
  const [primary, setPrimary] = useState(null)       // {ticker, name, cik}
  const [primaryFiling, setPrimaryFiling] = useState(null)
  const [primaryDash, setPrimaryDash] = useState(null)
  const [primaryLoading, setPrimaryLoading] = useState(false)
  const [primaryError, setPrimaryError] = useState(null)

  const [compareMode, setCompareMode] = useState(false)
  const [compareCompany, setCompareCompany] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState(null)

  const [showCosts, setShowCosts] = useState(false)

  // ── Theme: light by default 7am–7pm, dark otherwise; manual override persists ──
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('finsight-theme')
    if (saved) return saved
    const hour = new Date().getHours()
    return (hour >= 19 || hour < 7) ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('finsight-theme', theme)
  }, [theme])

  // Auto-switch on the hour boundary (7am → light, 7pm → dark) if not manually overridden
  useEffect(() => {
    const interval = setInterval(() => {
      const saved = localStorage.getItem('finsight-theme-manual')
      if (saved) return  // user made a manual choice — don't auto-switch
      const hour = new Date().getHours()
      setTheme(hour >= 19 || hour < 7 ? 'dark' : 'light')
    }, 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    localStorage.setItem('finsight-theme-manual', '1')  // mark as manual override
  }

  const handleSelectPrimary = async (company) => {
    setPrimary(company)
    setPrimaryFiling(null)
    setPrimaryDash(null)
    setPrimaryError(null)
    setPrimaryLoading(true)
    setComparison(null)
    setCompareCompany(null)

    try {
      const { ingest, dashboard } = await ingestAndDashboard(company.ticker)
      setPrimaryFiling(ingest)
      setPrimaryDash(dashboard)
    } catch (e) {
      setPrimaryError(e.response?.data?.detail || 'Failed to load filing.')
    } finally {
      setPrimaryLoading(false)
    }
  }

  const handleSelectCompare = async (company) => {
    if (!primary) return
    setCompareCompany(company)
    setComparison(null)
    setCompareError(null)
    setCompareLoading(true)

    try {
      const { data } = await axios.post(`${API_URL}/api/companies/compare`, {
        tickers: [primary.ticker, company.ticker],
      })
      setComparison(data)
    } catch (e) {
      setCompareError(e.response?.data?.detail || 'Comparison failed.')
    } finally {
      setCompareLoading(false)
    }
  }

  const exitCompare = () => {
    setCompareMode(false)
    setCompareCompany(null)
    setComparison(null)
    setCompareError(null)
  }

  const showCompare = compareMode && (compareLoading || comparison || compareError)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <TrendingUp size={20} />
          <span>FinSight</span>
        </div>

        <CompanySearch
          onSelect={handleSelectPrimary}
          placeholder="Search company (e.g. Apple, AAPL)…"
        />

        {primary && !compareMode && (
          <button
            className="btn-compare"
            onClick={() => setCompareMode(true)}
            title="Compare with another company"
          >
            <GitCompare size={14} />
            Compare
          </button>
        )}

        {compareMode && (
          <>
            <span className="compare-vs">vs</span>
            <CompanySearch
              onSelect={handleSelectCompare}
              placeholder="Add company to compare…"
            />
            <button className="btn-icon" onClick={exitCompare} title="Exit compare mode">
              <X size={16} />
            </button>
          </>
        )}

        {primary && (
          <div className="active-ticker">
            <span className="ticker-sym">{primary.ticker}</span>
            <span className="ticker-co">{primary.name}</span>
          </div>
        )}

        <StatusDots />
        <button className="btn-icon" onClick={toggleTheme} title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}>
          {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
        </button>
        <button className="btn-icon cost-btn" onClick={() => setShowCosts(true)} title="LLM Cost Tracker">
          <DollarSign size={15} />
        </button>
      </header>

      {showCosts && <CostPanel onClose={() => setShowCosts(false)} />}

      <main className="layout">
        {showCompare ? (
          <CompareView
            comparison={comparison}
            loading={compareLoading}
            error={compareError}
            onBack={exitCompare}
          />
        ) : (
          <PanelGroup direction="horizontal" className="panel-group">
            {/* Left column: Dashboard + Report — original static layout */}
            <Panel defaultSize={62} minSize={35} className="panel">
              <div className="panel-scroll chart-col">
                <Dashboard
                  company={primary}
                  dashboard={primaryDash}
                  loading={primaryLoading}
                  error={primaryError}
                />
                <ReportView
                  ticker={primary?.ticker ?? null}
                  ingesting={primaryLoading}
                />
              </div>
            </Panel>

            <PanelResizeHandle className="resize-handle resize-handle-v">
              <div className="resize-handle-bar" />
            </PanelResizeHandle>

            {/* Right column: Chat — drag to resize */}
            <Panel defaultSize={38} minSize={20} className="panel">
              <div className="panel-scroll">
                <FilingPanel
                  ticker={primary?.ticker ?? null}
                  companyName={primary?.name ?? ''}
                  filingId={primaryFiling?.filing_id ?? null}
                  filing={primaryFiling ? {
                    company_name: primary?.name,
                    filing_type: '10-K',
                    filed_date: primaryFiling.filed_date,
                    chunk_count: primaryFiling.chunk_count,
                  } : null}
                  fetchingFiling={primaryLoading}
                />
              </div>
            </Panel>
          </PanelGroup>
        )}
      </main>
    </div>
  )
}
