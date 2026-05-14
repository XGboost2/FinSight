import { create } from 'zustand'

function getAutoTheme() {
  const hour = new Date().getHours()
  return (hour >= 19 || hour < 7) ? 'dark' : 'light'
}

function getInitialTheme() {
  const saved = localStorage.getItem('finsight-theme')
  return saved || getAutoTheme()
}

export const useUIStore = create((set, get) => ({
  activeAnalyst: 'fundamentals',
  mountedTabs: new Set(),
  tabStatus: {},
  showCosts: false,
  theme: getInitialTheme(),

  setActiveAnalyst: (tab) => {
    set((state) => {
      const mounted = new Set(state.mountedTabs)
      if (tab !== 'fundamentals') mounted.add(tab)
      return { activeAnalyst: tab, mountedTabs: mounted }
    })
  },

  mountAllTabs: () => set({
    mountedTabs: new Set(['news', 'sentiment', 'risk', 'technical', 'bullbear']),
  }),

  resetTabs: () => set({
    activeAnalyst: 'fundamentals',
    mountedTabs: new Set(),
    tabStatus: {},
  }),

  updateTabStatus: (tab, status) =>
    set((state) => ({ tabStatus: { ...state.tabStatus, [tab]: status } })),

  setShowCosts: (show) => set({ showCosts: show }),

  toggleTheme: () => {
    const next = get().theme === 'light' ? 'dark' : 'light'
    set({ theme: next })
    localStorage.setItem('finsight-theme', next)
    localStorage.setItem('finsight-theme-manual', '1')
    document.documentElement.setAttribute('data-theme', next)
  },

  setTheme: (theme) => {
    set({ theme })
    localStorage.setItem('finsight-theme', theme)
    document.documentElement.setAttribute('data-theme', theme)
  },

  syncThemeToDOM: () => {
    document.documentElement.setAttribute('data-theme', get().theme)
  },

  tickAutoTheme: () => {
    const manual = localStorage.getItem('finsight-theme-manual')
    if (manual) return
    const auto = getAutoTheme()
    if (auto !== get().theme) {
      get().setTheme(auto)
    }
  },
}))
