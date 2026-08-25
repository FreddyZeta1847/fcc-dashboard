/*
 * Overview.tsx
 * The dashboard's landing page. Pure composition — mounts StatusPanel,
 * MoneySavedHeadline, and RecentRequestsFeed together. Each panel is
 * self-fetching (owns its own query), so this component adds no
 * data-fetching logic of its own; it only lays the three out. Mounted by
 * App once the backend-unreachable gate passes.
 */
import { StatusPanel } from '../components/StatusPanel'
import { MoneySavedHeadline } from '../components/MoneySavedHeadline'
import { RecentRequestsFeed } from '../components/RecentRequestsFeed'

export function Overview() {
  return (
    <div style={{ maxWidth: 1060 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.02em' }}>Overview</div>
        <div style={{ color: 'var(--muted)' }}>Is everything OK — and is it saving you money?</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.1fr) minmax(0,1fr)', gap: 20, alignItems: 'stretch' }}>
        <MoneySavedHeadline />
        <StatusPanel />
      </div>
      <div style={{ marginTop: 20 }}>
        <RecentRequestsFeed />
      </div>
    </div>
  )
}
