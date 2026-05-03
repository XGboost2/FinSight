import { useState } from 'react'
import axios from 'axios'
import { TrendingUp, GitCompare, X } from 'lucide-react'
import CompanySearch from './components/CompanySearch'
import Dashboard from './components/Dashboard'
import CompareView from './components/CompareView'
import FilingPanel from './components/FilingPanel'
import StatusDots from './components/StatusDots'
import ReportView from './components/ReportView'

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
      </header>

      <main className={`layout ${showCompare ? 'layout-full' : ''}`}>
        {showCompare ? (
          <CompareView
            comparison={comparison}
            loading={compareLoading}
            error={compareError}
            onBack={exitCompare}
          />
        ) : (
          <>
            <section className="chart-col">
              <Dashboard
                company={primary}
                dashboard={primaryDash}
                loading={primaryLoading}
                error={primaryError}
              />
              <ReportView ticker={primary?.ticker ?? null} />
            </section>
            <aside className="filing-col">
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
            </aside>
          </>
        )}
      </main>
    </div>
  )
}
