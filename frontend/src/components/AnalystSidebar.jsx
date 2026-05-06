import { BarChart2, Newspaper, Activity, Shield, LineChart, Scale } from 'lucide-react'

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

export default function AnalystSidebar({ activeTab, onTabChange, tabStatus = {} }) {
  return (
    <nav className="analyst-sidebar">
      <div className="sidebar-label">Analysts</div>
      {TABS.map(({ id, label, icon: Icon, sub }) => (
        <button
          key={id}
          className={`sidebar-tab${activeTab === id ? ' sidebar-tab-active' : ''}`}
          onClick={() => onTabChange(id)}
        >
          <Icon size={16} className="sidebar-tab-icon" />
          <div className="sidebar-tab-text">
            <span className="sidebar-tab-label">{label}</span>
            <span className="sidebar-tab-sub">{sub}</span>
          </div>
          <StatusDot status={tabStatus[id]} />
        </button>
      ))}
    </nav>
  )
}
