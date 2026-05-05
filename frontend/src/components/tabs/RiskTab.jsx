import { Shield, AlertTriangle, Calendar, Tag } from 'lucide-react'

const MOCK_RISKS = [
  'Concentration of revenue in key geographic markets exposes the company to macroeconomic and regulatory headwinds.',
  'Supply chain dependencies on single-source suppliers create margin vulnerability during component shortages.',
  'Ongoing antitrust investigations in the EU and US could result in material fines or operational restrictions.',
]

const MOCK_EVENTS = [
  { date: '2024-10-03', type: 'Legal',    summary: 'Regulatory investigation disclosed — potential fine of up to $2B' },
  { date: '2024-08-21', type: 'Earnings', summary: 'Q3 FY2024 earnings release — revenue $94.9B, EPS $1.40' },
  { date: '2024-07-15', type: 'Guidance', summary: 'FY2025 guidance updated: revenue growth of 5-7% expected' },
]

const EVENT_COLORS = {
  Legal:    'event-legal',
  Earnings: 'event-earnings',
  Guidance: 'event-guidance',
  Leadership: 'event-leadership',
}

export default function RiskTab({ ticker }) {
  return (
    <div className="tab-view">
      <div className="tab-agent-header glass-card">
        <div className="tab-agent-identity">
          <Shield size={18} className="tab-agent-icon" />
          <div>
            <span className="tab-agent-name">Risk Analyst</span>
            <span className="tab-agent-source">Item 1A · 8-K Events · YoY Diff</span>
          </div>
        </div>
        <span className="tab-agent-badge badge-pending">Backend pending</span>
      </div>

      <div className="tab-row-2col">
        <div className="tab-section glass-card">
          <div className="section-label">Risk Score</div>
          <div className="risk-score-hero">
            <span className="risk-score-num">34</span>
            <div>
              <span className="risk-hero-label risk-low">Low Risk</span>
              <p className="report-prose report-prose-sm">Manageable risk profile. Monitor regulatory developments.</p>
            </div>
          </div>
          <div className="gauge-track" style={{ marginTop: '0.75rem' }}>
            <div className="gauge-fill gauge-low" style={{ width: '34%' }} />
          </div>
        </div>

        <div className="tab-section glass-card">
          <div className="section-label">YoY Risk Shift</div>
          <div className="risk-yoy-stats">
            <div className="risk-yoy-stat">
              <span className="risk-yoy-num risk-new">+3</span>
              <span className="risk-yoy-desc">New risks</span>
            </div>
            <div className="risk-yoy-stat">
              <span className="risk-yoy-num risk-removed">−1</span>
              <span className="risk-yoy-desc">Resolved</span>
            </div>
            <div className="risk-yoy-stat">
              <span className="risk-yoy-num risk-changed">5</span>
              <span className="risk-yoy-desc">Evolved</span>
            </div>
          </div>
        </div>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">
          <AlertTriangle size={12} /> Top Risk Factors (Item 1A)
        </div>
        <ul className="risk-list-report">
          {MOCK_RISKS.map((r, i) => (
            <li key={i} className="risk-item-report">{r}</li>
          ))}
        </ul>
      </div>

      <div className="tab-section glass-card">
        <div className="section-label">
          <Calendar size={12} /> Recent 8-K Events
        </div>
        <div className="events-list">
          {MOCK_EVENTS.map((ev, i) => (
            <div key={i} className="event-row">
              <span className="event-date">{ev.date}</span>
              <span className={`event-tag ${EVENT_COLORS[ev.type] || 'event-other'}`}>
                <Tag size={10} /> {ev.type}
              </span>
              <p className="event-summary">{ev.summary}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="tab-placeholder-note">
        Live risk score and 8-K events will be computed by the Risk Analyst agent using Item 1A extraction and real-time EDGAR 8-K filings.
      </div>
    </div>
  )
}
