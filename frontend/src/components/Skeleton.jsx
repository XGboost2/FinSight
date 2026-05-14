export function SkeletonLine({ width = '100%', height = 14 }) {
  return <div className="skeleton-line" style={{ width, height }} />
}

export function SkeletonBlock({ height = 80 }) {
  return <div className="skeleton-block" style={{ height }} />
}

export function DashboardSkeleton() {
  return (
    <div className="dashboard" aria-busy="true" aria-label="Loading dashboard">
      <div className="dashboard-header glass-card">
        <div className="dashboard-title">
          <SkeletonLine width={60} height={20} />
          <SkeletonLine width={140} height={14} />
        </div>
      </div>
      <SkeletonBlock height={420} />
      <SkeletonBlock height={60} />
      <div className="metrics-grid">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="metric-card glass-card">
            <SkeletonLine width={70} height={10} />
            <SkeletonLine width={90} height={22} />
          </div>
        ))}
      </div>
    </div>
  )
}

export function ReportSkeleton() {
  return (
    <div className="report-view" aria-busy="true" aria-label="Loading report">
      <div className="report-header glass-card">
        <div className="report-title-row">
          <SkeletonLine width={40} height={20} />
          <SkeletonLine width={120} height={16} />
        </div>
      </div>
      <div className="glass-card" style={{ padding: '1rem 1.1rem' }}>
        <SkeletonLine width="90%" />
        <SkeletonLine width="75%" />
        <SkeletonLine width="85%" />
      </div>
      <div className="glass-card" style={{ padding: '1rem 1.1rem' }}>
        <SkeletonLine width={100} height={12} />
        <SkeletonBlock height={120} />
      </div>
    </div>
  )
}

export function TabSkeleton() {
  return (
    <div className="tab-view" aria-busy="true" aria-label="Loading content">
      <div className="glass-card" style={{ padding: '0.875rem 1.125rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <SkeletonLine width={20} height={20} />
          <div>
            <SkeletonLine width={120} height={16} />
            <SkeletonLine width={80} height={11} />
          </div>
        </div>
      </div>
      <div className="glass-card" style={{ padding: '1rem 1.125rem' }}>
        <SkeletonLine width="80%" />
        <SkeletonLine width="65%" />
        <SkeletonLine width="70%" />
      </div>
      <div className="glass-card" style={{ padding: '1rem 1.125rem' }}>
        <SkeletonBlock height={100} />
      </div>
    </div>
  )
}
