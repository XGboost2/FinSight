import { useEffect, useState } from 'react'
import axios from 'axios'
import { TrendingUp, GitCompare, X, DollarSign, Sun, Moon } from 'lucide-react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'

import { useCompanyStore } from './stores/companyStore'
import { useCompareStore } from './stores/compareStore'
import { useUIStore } from './stores/uiStore'

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

const API_URL = import.meta.env.VITE_API_URL ?? ''
const SESSION_KEY = 'finsight-session-id'

export default function App() {
  const [sessionId, setSessionId] = useState(() => {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) return saved
    const id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
    return id
  })

  const {
    primary, primaryFiling, primaryDash,
    primaryLoading, primaryStep, primaryError,
    selectPrimary, restoreFromStorage, goHome: companyGoHome,
  } = useCompanyStore()

  const {
    compareMode, compareCompany, comparison,
    compareLoading, compareError,
    enterCompareMode, exitCompare: compareExit, selectCompare, reset: compareReset,
  } = useCompareStore()

  const {
    activeAnalyst, mountedTabs, tabStatus, showCosts, theme,
    setActiveAnalyst, mountAllTabs, resetTabs, updateTabStatus,
    setShowCosts, toggleTheme, syncThemeToDOM, tickAutoTheme,
  } = useUIStore()

  // Sync theme to DOM on mount
  useEffect(() => {
    syncThemeToDOM()
  }, [])

  // Auto-theme tick every 60s
  useEffect(() => {
    const interval = setInterval(tickAutoTheme, 60_000)
    return () => clearInterval(interval)
  }, [])

  // Restore last company on mount
  useEffect(() => {
    restoreFromStorage()
  }, [])

  // Reset session on 401 (expired TTL)
  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      res => res,
      err => {
        if (err.response?.status === 401) {
          const newId = crypto.randomUUID()
          localStorage.setItem(SESSION_KEY, newId)
          setSessionId(newId)
        }
        return Promise.reject(err)
      }
    )
    return () => axios.interceptors.response.eject(interceptor)
  }, [])

  const handleSelectPrimary = async (company) => {
    compareReset()
    resetTabs()
    await selectPrimary(company)
    mountAllTabs()
  }

  const handleSelectCompare = (company) => {
    if (!primary) return
    selectCompare(primary.ticker, company)
  }

  const exitCompare = () => {
    compareExit()
  }

  const goHome = () => {
    companyGoHome()
    resetTabs()
    compareReset()
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
          <button className="btn-compare" onClick={enterCompareMode} title="Compare with another company">
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
                  {mountedTabs.has('news') && (
                    <div style={{ display: activeAnalyst === 'news' ? 'contents' : 'none' }}>
                      <NewsTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('news', s)} />
                    </div>
                  )}
                  {mountedTabs.has('sentiment') && (
                    <div style={{ display: activeAnalyst === 'sentiment' ? 'contents' : 'none' }}>
                      <SentimentTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('sentiment', s)} />
                    </div>
                  )}
                  {mountedTabs.has('risk') && (
                    <div style={{ display: activeAnalyst === 'risk' ? 'contents' : 'none' }}>
                      <RiskTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('risk', s)} />
                    </div>
                  )}
                  {mountedTabs.has('technical') && (
                    <div style={{ display: activeAnalyst === 'technical' ? 'contents' : 'none' }}>
                      <TechnicalTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('technical', s)} />
                    </div>
                  )}
                  {mountedTabs.has('bullbear') && (
                    <div style={{ display: activeAnalyst === 'bullbear' ? 'contents' : 'none' }}>
                      <BullBearTab ticker={primary.ticker} onStatusChange={s => updateTabStatus('bullbear', s)} />
                    </div>
                  )}
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
                    sessionId={sessionId}
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
