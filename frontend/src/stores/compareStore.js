import { create } from 'zustand'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL ?? ''

export const useCompareStore = create((set) => ({
  compareMode: false,
  compareCompany: null,
  comparison: null,
  compareLoading: false,
  compareError: null,

  enterCompareMode: () => set({ compareMode: true }),

  exitCompare: () => set({
    compareMode: false,
    compareCompany: null,
    comparison: null,
    compareError: null,
  }),

  selectCompare: async (primaryTicker, company) => {
    set({
      compareCompany: company,
      comparison: null,
      compareError: null,
      compareLoading: true,
    })

    try {
      const { data } = await axios.post(`${API_URL}/api/companies/compare`, {
        tickers: [primaryTicker, company.ticker],
      })
      set({ comparison: data })
    } catch (e) {
      set({ compareError: e.response?.data?.detail || 'Comparison failed.' })
    } finally {
      set({ compareLoading: false })
    }
  },

  reset: () => set({
    compareMode: false,
    compareCompany: null,
    comparison: null,
    compareLoading: false,
    compareError: null,
  }),
}))
