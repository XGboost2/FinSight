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
import LandingPage from './components/LandingPage'
import AnalystSidebar from './components/AnalystSidebar'
import NewsTab from './components/tabs/NewsTab'
import SentimentTab from './components/tabs/SentimentTab'
import RiskTab from './components/tabs/RiskTab'
import TechnicalTab from './components/tabs/TechnicalTab'
import BullBearTab from './components/tabs/BullBearTab'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const POLL_INTERVAL = 3000   // 3s polling for task status
const POLL_TIMEOUT  = 300000 // 5 min max wait

async function pollIngestStatus(ticker, taskId, onStep) {
  const start = Date.now()
  while (Date.now() - start < POLL_TIMEOUT) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL))
    const { data } = await axios.get(`${API_URL}/api/companies/${ticker}/ingest/status?task_id=${taskId}`)
    if (data.step) onStep(data.step)
    if (data.status === 'done')  return data.result
    if (data.status === 'error') throw new Error(data.error || 'Ingest failed')
  }
  throw new Error('Ingest timed out after 5 minutes')
}

async function ingestAndDashboard(ticker, onStep) {
  const { data: ingest } = await axios.post(`${API_URL}/api/companies/${ticker}/ingest`)

  if (ingest.status !== 'cached' && ingest.task_id) {
    onStep('Fetching 10-K, 10-Q and 8-K from SEC EDGAR…')
    await pollIngestStatus(ticker, ingest.task_id, onStep)
    // Re-call ingest — now returns cached with real filing_id, chunk_count, filed_date
    const { data: cached } = await axios.post(`${API_URL}/api/companies/${ticker}/ingest`)
    const { data: dash } = await axios.get(`${API_URL}/api/companies/${ticker}/dashboard`)
    return { ingest: cached, dashboard: dash }
  }

  const { data: dash } = await axios.get(`${API_URL}/api/companies/${ticker}/dashboard`)
  return { ingest, dashboard: dash }
}

export default function App() {
  const [primary, setPrimary] = useState(null)
  const [primaryFiling, setPrimaryFiling] = useState(null)
  const [primaryDash, setPrimaryDash] = useState(null)
  const [primaryLoading, setPrimaryLoading] = useState(false)
  const [primaryStep, setPrimaryStep] = useState('')
  const [primaryError, setPrimaryError] = useState(null)

  const [compareMode, setCompareMode] = useState(false)
  const [compareCompany, setCompareCompany] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState(null)

  const [showCosts, setShowCosts] = useState(false)
  const [activeAnalyst, setActiveAnalyst] = useState('fundamentals')
  const [tabStatus, setTabStatus] = useState({})

  const updateTabStatus = (tab, status) =>
    setTabStatus(prev => ({ ...prev, [tab]: status }))

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

  useEffect(() => {
    const interval = setInterval(() => {
      const saved = localStorage.getItem('finsight-theme-manual')
      if (saved) return
      const hour = new Date().getHours()
      setTheme(hour >= 19 || hour < 7 ? 'dark' : 'light')
    }, 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    localStorage.setItem('finsight-theme-manual', '1')
  }

  const handleSelectPrimary = async (company) => {
    setPrimary(company)
    setPrimaryFiling(null)
    setPrimaryDash(null)
    setPrimaryError(null)
    setPrimaryLoading(true)
    setPrimaryStep('Queuing EDGAR agent…')
    setComparison(null)
    setCompareCompany(null)
    setCompareMode(false)
    setActiveAnalyst('fundamentals')
    setTabStatus({})

    try {
      const { ingest, dashboard } = await ingestAndDashboard(
        company.ticker,
        (step) => setPrimaryStep(step),
      )
      setPrimaryFiling(ingest)
      setPrimaryDash(dashboard)
    } catch (e) {
      setPrimaryError(e.response?.data?.detail || e.message || 'Failed to load filing.')
    } finally {
      setPrimaryLoading(false)
      setPrimaryStep('')
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

  const goHome = () => {
    setPrimary(null)
    setPrimaryFiling(null)
    setPrimaryDash(null)
    setPrimaryError(null)
    setActiveAnalyst('fundamentals')
    exitCompare()
  }

  const showCompare = compareMode && (compareLoading || comparison || compareError)

  if (!primary) {
    return (
      <div className="app">
        <LandingPage onSelect={handleSelectPrimary} theme={theme} onToggleTheme={toggleTheme} />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand brand-btn" onClick={goHome} title="Back to home">
          <TrendingUp size={20} />
          <span>FinSight</span>
        </button>

        <CompanySearch
          onSelect={handleSelectPrimary}
          placeholder="Search company (e.g. Apple, AAPL)…"
        />

        {!compareMode && (
          <button className="btn-compare" onClick={() => setCompareMode(true)} title="Compare with another company">
            <GitCompare size={14} /> Compare
          </button>
        )}

        {compareMode && (
          <>
            <span className="compare-vs">vs</span>
            <CompanySearch onSelect={handleSelectCompare} placeholder="Add company to compare…" />
            <button className="btn-icon" onClick={exitCompare} title="Exit compare mode">
              <X size={16} />
            </button>
          </>
        )}

        <div className="active-ticker">
          <span className="ticker-sym">{primary.ticker}</span>
          <span className="ticker-co">{primary.name}</span>
        </div>

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
          <div className="workspace">
            <AnalystSidebar activeTab={activeAnalyst} onTabChange={setActiveAnalyst} tabStatus={tabStatus} />

            <PanelGroup direction="horizontal" className="panel-group">
              <Panel defaultSize={62} minSize={35} className="panel">
                <div className="panel-scroll chart-col">
                  {activeAnalyst === 'fundamentals' && (
                    <>
                      <Dashboard
                        company={primary}
                        dashboard={primaryDash}
                        loading={primaryLoading}
                        loadingStep={primaryStep}
                        error={primaryError}
                      />
                      <ReportView
                        ticker={primary?.ticker ?? null}
                        ingesting={primaryLoading}
                        onStatusChange={s => updateTabStatus('fundamentals', s)}
                      />
                    </>
                  )}
                  {activeAnalyst === 'news'      && <NewsTab      ticker={primary.ticker} onStatusChange={s => updateTabStatus('news', s)} />}
                  {activeAnalyst === 'sentiment' && <SentimentTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('sentiment', s)} />}
                  {activeAnalyst === 'risk'      && <RiskTab      ticker={primary.ticker} onStatusChange={s => updateTabStatus('risk', s)} />}
                  {activeAnalyst === 'technical' && <TechnicalTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('technical', s)} />}
                  {activeAnalyst === 'bullbear'  && <BullBearTab  ticker={primary.ticker} onStatusChange={s => updateTabStatus('bullbear', s)} />}
                </div>
              </Panel>

              <PanelResizeHandle className="resize-handle resize-handle-v">
                <div className="resize-handle-bar" />
              </PanelResizeHandle>

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
          </div>
        )}
      </main>
    </div>
  )
}
