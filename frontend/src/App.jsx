import { useState, useEffect } from 'react'
import axios from 'axios'
import { ShieldCheck, Activity, Lock, Database } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [apiStatus, setApiStatus] = useState('loading')
  const [apiMessage, setApiMessage] = useState('')

  useEffect(() => {
    const checkApi = async () => {
      try {
        const response = await axios.get(`${API_URL}/`)
        setApiMessage(response.data.message)
        setApiStatus('connected')
      } catch (error) {
        console.error('API Connection Error:', error)
        setApiStatus('error')
        setApiMessage('Unable to connect to backend API')
      }
    }

    checkApi()
  }, [])

  return (
    <div className="app-container">
      <header className="header">
        <h1>FinSec Platform</h1>
        <p>Next-Generation Financial Security Ecosystem</p>
        
        <div className={`status-badge ${apiStatus}`}>
          <div className="pulse"></div>
          {apiStatus === 'loading' && 'Connecting to Backend...'}
          {apiStatus === 'connected' && 'System Online'}
          {apiStatus === 'error' && 'Connection Failed'}
        </div>
      </header>

      <div className="dashboard-grid">
        <div className="glass-card">
          <h2>System Status</h2>
          <div className="feature-item">
            <div className="feature-icon">
              <Activity size={24} />
            </div>
            <div className="feature-content">
              <h3>API Connection</h3>
              <p>{apiMessage || 'Awaiting signal...'}</p>
            </div>
          </div>
          <div className="feature-item">
            <div className="feature-icon">
              <Database size={24} />
            </div>
            <div className="feature-content">
              <h3>Database</h3>
              <p>Ready for initialization</p>
            </div>
          </div>
        </div>

        <div className="glass-card">
          <h2>Security Modules</h2>
          <div className="feature-item">
            <div className="feature-icon">
              <ShieldCheck size={24} />
            </div>
            <div className="feature-content">
              <h3>Threat Detection</h3>
              <p>Real-time transaction monitoring</p>
            </div>
          </div>
          <div className="feature-item">
            <div className="feature-icon">
              <Lock size={24} />
            </div>
            <div className="feature-content">
              <h3>End-to-End Encryption</h3>
              <p>Military-grade data protection</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
