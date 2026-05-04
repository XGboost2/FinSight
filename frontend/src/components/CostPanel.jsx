import { useEffect, useState } from 'react'
import axios from 'axios'
import { DollarSign, RefreshCw, Loader, X } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function fmt(n) {
  if (!n) return '$0.000000'
  return `$${Number(n).toFixed(6)}`
}

function PeriodCard({ title, data }) {
  if (!data) return null
  const models = Object.entries(data.by_model || {})
  return (
    <div className="cost-period-card glass-card">
      <div className="cost-period-title">{title}</div>
      <div className="cost-period-total">
        <span className="cost-total-amt">{fmt(data.total_cost)}</span>
        <span className="cost-total-calls">{data.total_calls} calls</span>
      </div>
      {models.length > 0 && (
        <table className="cost-model-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Cost</th>
              <th>Calls</th>
              <th>Tok In</th>
              <th>Tok Out</th>
            </tr>
          </thead>
          <tbody>
            {models.map(([model, m]) => (
              <tr key={model}>
                <td className="cost-model-name">{model}</td>
                <td>{fmt(m.cost)}</td>
                <td>{m.calls}</td>
                <td>{m.tokens_in?.toLocaleString()}</td>
                <td>{m.tokens_out?.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {models.length === 0 && <div className="cost-empty">No calls yet</div>}
    </div>
  )
}

function DailyRow({ day }) {
  return (
    <tr>
      <td>{day.date}</td>
      <td>{fmt(day.total_cost)}</td>
      <td>{day.total_calls}</td>
    </tr>
  )
}

export default function CostPanel({ onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchCosts = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data: d } = await axios.get(`${API_URL}/api/admin/costs`)
      setData(d)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load costs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCosts() }, [])

  return (
    <div className="cost-panel-overlay" onClick={onClose}>
      <div className="cost-panel glass-card" onClick={e => e.stopPropagation()}>
        <div className="cost-panel-header">
          <div className="cost-panel-title">
            <DollarSign size={16} />
            <span>LLM Cost Tracker</span>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button className="btn-refresh" onClick={fetchCosts} title="Refresh">
              <RefreshCw size={12} /> Refresh
            </button>
            <button className="btn-icon" onClick={onClose} title="Close">
              <X size={16} />
            </button>
          </div>
        </div>

        {loading && (
          <div className="cost-loading">
            <Loader size={16} className="spin" />
            <span>Loading costs…</span>
          </div>
        )}

        {error && <div className="cost-error">{error}</div>}

        {data && !loading && (
          <>
            <div className="cost-periods-row">
              <PeriodCard title="Today" data={data.today} />
              <PeriodCard title="This Week" data={data.week} />
              <PeriodCard title="This Month" data={data.month} />
            </div>

            <div className="cost-history glass-card">
              <div className="cost-period-title">Last 7 Days</div>
              <table className="cost-model-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Total Cost</th>
                    <th>Calls</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.last_7_days || []).map(d => (
                    <DailyRow key={d.date} day={d} />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
