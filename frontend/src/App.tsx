/*
 * App.tsx
 * Root component and the app-level "backend unreachable" resilience gate.
 * Calls useStatus() itself (not delegated to a child) so a network-level
 * failure — the dashboard's OWN backend not running — can short-circuit
 * the whole dashboard before any panel mounts. This is deliberately a
 * different failure mode from `fcc_status: "down"`, which is a *successful*
 * response and is FCC being down, not our backend: see useStatus.ts. The
 * "backend reachable" branch mounts the full Overview page (Task 6), which
 * composes StatusPanel, MoneySavedHeadline, and RecentRequestsFeed.
 */
import { useStatus } from './hooks/useStatus'
import { Overview } from './pages/Overview'

function App() {
  const { isLoading, isError } = useStatus()

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
      <Overview />
    </div>
  )
}

export default App
