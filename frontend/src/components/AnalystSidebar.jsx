import { BarChart2, Newspaper, Activity, Shield, LineChart, Scale, Menu, X } from 'lucide-react'
import { useState } from 'react'

const TABS = [
  { id: 'fundamentals', label: 'Fundamentals', icon: BarChart2,  sub: '10-K · XBRL'       },
  { id: 'news',         label: 'News',         icon: Newspaper,  sub: 'Market feed'        },
  { id: 'sentiment',    label: 'Sentiment',    icon: Activity,   sub: 'MD&A tone'          },
  { id: 'risk',         label: 'Risk',         icon: Shield,     sub: 'Item 1A · 8-K'      },
  { id: 'technical',    label: 'Technical',    icon: LineChart,  sub: 'RSI · MACD'         },
  { id: 'bullbear',     label: 'Bull vs Bear', icon: Scale,      sub: 'Debate'             },
]

function StatusDot({ status }) {
  if (!status) return null
  if (status === 'loading') return <span className="tab-status-dot tab-status-loading" />
  if (status === 'done')    return <span className="tab-status-dot tab-status-done" />
  if (status === 'error')   return <span className="tab-status-dot tab-status-error" />
  return null
}

function SidebarContent({ activeTab, onTabChange, tabStatus }) {
  return (
    <>
      <div className="sidebar-label" id="analyst-sidebar-label">Analysts</div>
      {TABS.map(({ id, label, icon: Icon, sub }) => (
        <button
          key={id}
          role="tab"
          aria-selected={activeTab === id}
          aria-controls={`tabpanel-${id}`}
          id={`tab-${id}`}
          className={`sidebar-tab${activeTab === id ? ' sidebar-tab-active' : ''}`}
          onClick={() => onTabChange(id)}
        >
          <Icon size={16} className="sidebar-tab-icon" aria-hidden="true" />
          <div className="sidebar-tab-text">
            <span className="sidebar-tab-label">{label}</span>
            <span className="sidebar-tab-sub">{sub}</span>
          </div>
          <StatusDot status={tabStatus[id]} />
        </button>
      ))}
    </>
  )
}

export default function AnalystSidebar({ activeTab, onTabChange, tabStatus = {} }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleTabChange = (id) => {
    onTabChange(id)
    setMobileOpen(false)
  }

  return (
    <>
      {/* Mobile hamburger trigger */}
      <button
        className="sidebar-mobile-trigger"
        onClick={() => setMobileOpen(true)}
        aria-label="Open analyst menu"
      >
        <Menu size={18} />
        <span className="sidebar-mobile-label">
          {TABS.find(t => t.id === activeTab)?.label || 'Analysts'}
        </span>
      </button>

      {/* Desktop sidebar */}
      <nav className="analyst-sidebar analyst-sidebar-desktop" role="tablist" aria-label="Analysis views" aria-orientation="vertical">
        <SidebarContent activeTab={activeTab} onTabChange={handleTabChange} tabStatus={tabStatus} />
      </nav>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="sidebar-drawer-overlay" onClick={() => setMobileOpen(false)}>
          <nav
            className="sidebar-drawer"
            role="tablist"
            aria-label="Analysis views"
            onClick={e => e.stopPropagation()}
          >
            <div className="sidebar-drawer-header">
              <span className="sidebar-label">Analysts</span>
              <button className="btn-icon" onClick={() => setMobileOpen(false)} aria-label="Close menu">
                <X size={16} />
              </button>
            </div>
            <SidebarContent activeTab={activeTab} onTabChange={handleTabChange} tabStatus={tabStatus} />
          </nav>
        </div>
      )}
    </>
  )
}
