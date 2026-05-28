import { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL ?? ''
const POLL_MS = 30_000

function Dot({ ok, label }) {
  return (
    <div className="status-dot-item" title={`${label}: ${ok === null ? 'checking…' : ok ? 'online' : 'offline'}`}>
      <span className={`status-dot ${ok === null ? 'status-checking' : ok ? 'status-ok' : 'status-err'}`} />
      <span className="status-label">{label}</span>
    </div>
  )
}

export default function StatusDots() {
  const [redis, setRedis] = useState(null)
  const [qdrant, setQdrant] = useState(null)

  const poll = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/api/health`, { timeout: 5000 })
      setRedis(data.redis_ok)
      setQdrant(data.qdrant_ok)
    } catch {
      setRedis(false)
      setQdrant(false)
    }
  }

  useEffect(() => {
    poll()
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="status-dots">
      <Dot ok={redis} label="Redis" />
      <Dot ok={qdrant} label="Qdrant" />
    </div>
  )
}