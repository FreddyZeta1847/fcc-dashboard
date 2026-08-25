/*
 * App.tsx
 * Root component: the app-level "backend unreachable" resilience gate,
 * plus the Sidebar + main-content layout. Calls useStatus() itself (not
 * delegated to a child) so a network-level failure — the dashboard's OWN
 * backend not running — can short-circuit the whole dashboard before any
 * tab content mounts. This is deliberately a different failure mode from
 * `fcc_status: "down"`, which is a *successful* response and is FCC being
 * down, not our backend: see useStatus.ts. The isLoading/isError branches
 * are evaluated first and unconditionally on tab state — a user who
 * switched tabs and then the backend goes down must still see this
 * screen, not a broken page — so the tab useState and Sidebar render
 * only past both branches, in the "backend reachable" return.
 */
import { useState } from 'react'
import { useStatus } from './hooks/useStatus'
import { Overview } from './pages/Overview'
import { Usage } from './pages/Usage'
import { Database } from './pages/Database'
import { Settings } from './pages/Settings'
import { Sidebar, type Tab } from './components/Sidebar'

function App() {
  const { isLoading, isError } = useStatus()
  const [tab, setTab] = useState<Tab>('overview')

  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg)',
          color: 'var(--text)',
        }}
      >
        <p>Loading…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg)',
          color: 'var(--text)',
          padding: 40,
        }}
      >
        <div
          style={{
            maxWidth: 440,
            textAlign: 'center',
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 20,
            padding: '48px 40px',
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'var(--redT)',
              border: '1px solid var(--redB)',
              margin: '0 auto 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: 'var(--red)' }} />
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 800, marginBottom: 8 }}>Backend not running</h1>
          <p style={{ color: 'var(--muted)' }}>Start the dashboard backend, then reload this page.</p>
        </div>
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        background: 'var(--bg)',
        color: 'var(--text)',
        fontFamily: "'Manrope', ui-sans-serif, sans-serif",
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      <Sidebar activeTab={tab} onTabChange={setTab} />
      <main style={{ flex: 1, minWidth: 0, padding: '36px 44px 60px', boxSizing: 'border-box' }}>
        {tab === 'overview' && <Overview />}
        {tab === 'usage' && <Usage />}
        {tab === 'settings' && <Settings />}
        {tab === 'database' && <Database />}
      </main>
    </div>
  )
}

export default App
