import { create } from 'zustand'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const POLL_INTERVAL = 3000
const POLL_TIMEOUT = 300000
const TICKER_RE = /^[A-Z0-9.\-]{1,10}$/

function isValidCompany(obj) {
  return obj
    && typeof obj === 'object'
    && typeof obj.ticker === 'string'
    && typeof obj.name === 'string'
    && TICKER_RE.test(obj.ticker.toUpperCase())
}

async function pollIngestStatus(ticker, taskId, onStep) {
  const start = Date.now()
  while (Date.now() - start < POLL_TIMEOUT) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL))
    const { data } = await axios.get(`${API_URL}/api/companies/${ticker}/ingest/status?task_id=${taskId}`)
    if (data.step) onStep(data.step)
    if (data.status === 'done') return data.result
    if (data.status === 'error') throw new Error(data.error || 'Ingest failed')
  }
  throw new Error('Ingest timed out after 5 minutes')
}

async function ingestAndDashboard(ticker, onStep) {
  const { data: ingest } = await axios.post(`${API_URL}/api/companies/${ticker}/ingest`)

  if (ingest.status !== 'cached' && ingest.task_id) {
    onStep('Fetching 10-K, 10-Q and 8-K from SEC EDGAR…')
    await pollIngestStatus(ticker, ingest.task_id, onStep)
    const { data: cached } = await axios.post(`${API_URL}/api/companies/${ticker}/ingest`)
    const { data: dash } = await axios.get(`${API_URL}/api/companies/${ticker}/dashboard`)
    return { ingest: cached, dashboard: dash }
  }

  const { data: dash } = await axios.get(`${API_URL}/api/companies/${ticker}/dashboard`)
  return { ingest, dashboard: dash }
}

export const useCompanyStore = create((set, get) => ({
  primary: null,
  primaryFiling: null,
  primaryDash: null,
  primaryLoading: false,
  primaryStep: '',
  primaryError: null,

  selectPrimary: async (company) => {
    localStorage.setItem('finsight-last-company', JSON.stringify(company))
    set({
      primary: company,
      primaryFiling: null,
      primaryDash: null,
      primaryError: null,
      primaryLoading: true,
      primaryStep: 'Queuing EDGAR agent…',
    })

    try {
      const { ingest, dashboard } = await ingestAndDashboard(
        company.ticker,
        (step) => set({ primaryStep: step }),
      )
      set({ primaryFiling: ingest, primaryDash: dashboard })
    } catch (e) {
      set({ primaryError: e.response?.data?.detail || e.message || 'Failed to load filing.' })
    } finally {
      set({ primaryLoading: false, primaryStep: '' })
    }
  },

  restoreFromStorage: () => {
    const saved = localStorage.getItem('finsight-last-company')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (isValidCompany(parsed)) {
          get().selectPrimary(parsed)
        } else {
          localStorage.removeItem('finsight-last-company')
        }
      } catch {
        localStorage.removeItem('finsight-last-company')
      }
    }
  },

  goHome: () => {
    localStorage.removeItem('finsight-last-company')
    set({
      primary: null,
      primaryFiling: null,
      primaryDash: null,
      primaryError: null,
    })
  },
}))
