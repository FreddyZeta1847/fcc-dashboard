/*
 * Settings.tsx
 * The dashboard's Settings page. Pure composition — mounts PricingEditor
 * and PriceRefreshFlow. FCC process control lives only in the sidebar's
 * stateful Run/Stop button now (Sidebar.tsx) — Settings no longer
 * duplicates it. Each child is self-fetching (owns its own query/mutation
 * hooks), so this component adds no data-fetching logic of its own; it
 * only lays them out, each in its own Card (rendered by the child
 * components themselves).
 */
import { PricingEditor } from '../components/PricingEditor'
import { PriceRefreshFlow } from '../components/PriceRefreshFlow'

export function Settings() {
  return (
    <div style={{ maxWidth: 1060 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.02em' }}>Settings</div>
        <div style={{ color: 'var(--muted)' }}>
          Pricing — every action here confirms before it fires
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <PricingEditor />
        <PriceRefreshFlow />
      </div>
    </div>
  )
}
