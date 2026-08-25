/*
 * App.tsx
 * Root component and the app-level "backend unreachable" resilience gate.
 * Calls useStatus() itself (not delegated to a child) so a network-level
 * failure — the dashboard's OWN backend not running — can short-circuit
 * the whole dashboard before any tab content mounts. This is deliberately
 * a different failure mode from `fcc_status: "down"`, which is a
 * *successful* response and is FCC being down, not our backend: see
 * useStatus.ts. The isLoading/isError branches are evaluated first and
 * unconditionally on tab state — a user who switched tabs and then the
 * backend goes down must still see this screen, not a broken page — so
 * the tab useState and Nav render only past both branches, in the
 * "backend reachable" return. Task 1 adds the tab shell (Overview, Usage,
 * Settings, Database); Task 3 wires in the real Database page. Settings
 * still renders a placeholder until Task 7 builds it.
 */
import { useState } from 'react'
import { useStatus } from './hooks/useStatus'
import { Overview } from './pages/Overview'
import { Database } from './pages/Database'
import { Nav, type Tab } from './components/Nav'

function App() {
  const { isLoading, isError } = useStatus()
  const [tab, setTab] = useState<Tab>('overview')

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-red-50">
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-red-700">Backend not running</h1>
          <p className="text-red-600">Start the dashboard backend, then reload this page.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <h1 className="text-2xl font-semibold p-4">FCC Dashboard</h1>
      <Nav activeTab={tab} onTabChange={setTab} />
      {tab === 'overview' && <Overview />}
      {tab === 'usage' && <div className="p-4">Usage — coming soon</div>}
      {tab === 'settings' && <div className="p-4">Settings — coming soon</div>}
      {tab === 'database' && <Database />}
    </div>
  )
}

export default App
