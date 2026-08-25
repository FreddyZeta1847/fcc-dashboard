/*
 * Sidebar.tsx
 * Vertical, collapsible navigation for the dashboard's four pages —
 * replaces the earlier horizontal Nav.tsx tab bar with the approved
 * design's sidebar layout. Stateless/controlled for tab selection, same
 * as its predecessor: App.tsx owns which tab is active (local useState)
 * and passes it down, so the "backend unreachable" resilience gate in
 * App.tsx can keep short-circuiting the whole app regardless of nav
 * state. The collapsed state and theme toggle are visual-only concerns
 * owned locally here — neither affects App's resilience gate or which
 * tab is active.
 *
 * The Run/Stop button is stateful: it reads `useStatus()` (the same
 * `/status` poll StatusPanel already uses — TanStack Query dedupes the
 * two subscriptions onto one network call, same `queryKey`) to show
 * "Run fcc-server" while `fcc_status === "down"` and "Stop fcc-server"
 * while `"up"`, and fires the matching mutation. This is now the ONLY
 * place FCC start/stop lives — Settings' ProcessControls was removed as
 * a duplicate once this button covered both directions correctly. On
 * success it invalidates the `['status']` query so the button flips
 * immediately instead of waiting for the next 10s poll.
 */
import { useState, type ReactElement } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTheme } from '../hooks/useTheme'
import { useStatus } from '../hooks/useStatus'
import { useControlStart, useControlStop } from '../hooks/useControl'
import { startMessage, stopMessage } from '../lib/processControlMessages'
import { ConfirmDialog } from './ConfirmDialog'
import { Toast } from './Toast'

export type Tab = 'overview' | 'usage' | 'settings' | 'database'

const TABS: { id: Tab; label: string; icon: ReactElement }[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="2" width="6" height="6" rx="2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="10" y="2" width="6" height="6" rx="2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="2" y="10" width="6" height="6" rx="2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="10" y="10" width="6" height="6" rx="2" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    ),
  },
  {
    id: 'usage',
    label: 'Usage',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <rect x="2" y="9" width="3.5" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="7.25" y="5" width="3.5" height="11" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
        <rect x="12.5" y="2" width="3.5" height="14" rx="1.2" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    ),
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <line x1="2" y1="6" x2="16" y2="6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="6" cy="6" r="2.2" fill="var(--panel)" stroke="currentColor" strokeWidth="1.6" />
        <line x1="2" y1="12.5" x2="16" y2="12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="12" cy="12.5" r="2.2" fill="var(--panel)" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    ),
  },
  {
    id: 'database',
    label: 'Database',
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <ellipse cx="9" cy="4" rx="6.5" ry="2.4" stroke="currentColor" strokeWidth="1.6" />
        <path d="M2.5 4v10c0 1.3 2.9 2.4 6.5 2.4s6.5-1.1 6.5-2.4V4" stroke="currentColor" strokeWidth="1.6" />
        <path d="M2.5 9c0 1.3 2.9 2.4 6.5 2.4s6.5-1.1 6.5-2.4" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    ),
  },
]

interface SidebarProps {
  activeTab: Tab
  onTabChange: (tab: Tab) => void
}

const navButtonBaseStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  width: '100%',
  padding: '10px 12px',
  border: 'none',
  borderRadius: 10,
  cursor: 'pointer',
  font: 'inherit',
  textAlign: 'left' as const,
}

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const expanded = !collapsed

  const queryClient = useQueryClient()
  const { data: status } = useStatus()
  const fccUp = status?.fcc_status === 'up'

  const startMutation = useControlStart()
  const stopMutation = useControlStop()
  const runMutation = fccUp ? stopMutation : startMutation
  const [confirmingRun, setConfirmingRun] = useState(false)
  const [runToast, setRunToast] = useState<{ title: string; body: string } | null>(null)

  function handleRunConfirm() {
    if (fccUp) {
      stopMutation.mutate(undefined, {
        onSuccess: (result) => {
          setConfirmingRun(false)
          setRunToast({ title: 'Stop fcc-server', body: stopMessage(result.action) })
          queryClient.invalidateQueries({ queryKey: ['status'] })
        },
        onError: () => setConfirmingRun(false),
      })
      return
    }
    startMutation.mutate(undefined, {
      onSuccess: (result) => {
        setConfirmingRun(false)
        setRunToast({ title: 'Run fcc-server', body: startMessage(result.action) })
        queryClient.invalidateQueries({ queryKey: ['status'] })
      },
      onError: () => setConfirmingRun(false),
    })
  }

  return (
    <aside
      style={{
        width: collapsed ? 68 : 236,
        flexShrink: 0,
        background: 'var(--panel)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '20px 12px',
        gap: 4,
        transition: 'width .2s ease',
        position: 'sticky',
        top: 0,
        height: '100vh',
        boxSizing: 'border-box',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 10px 20px' }}>
        <div
          aria-hidden="true"
          style={{
            width: 32,
            height: 32,
            flexShrink: 0,
            borderRadius: 9,
            background: 'linear-gradient(135deg, oklch(0.7 0.15 250), oklch(0.65 0.16 300))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: 13,
            color: '#fff',
            letterSpacing: '.5px',
          }}
        >
          FC
        </div>
        {expanded && (
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 15, whiteSpace: 'nowrap' }}>FCC Dashboard</div>
            <div style={{ fontSize: 11, color: 'var(--faint)', whiteSpace: 'nowrap' }}>free-claude-code</div>
          </div>
        )}
      </div>

      {TABS.map(({ id, label, icon }) => {
        const isActive = id === activeTab
        return (
          <button
            key={id}
            type="button"
            title={label}
            onClick={() => onTabChange(id)}
            style={{
              ...navButtonBaseStyle,
              fontSize: 14,
              fontWeight: 700,
              background: isActive ? 'var(--card2)' : 'transparent',
              color: isActive ? 'var(--text)' : 'var(--muted)',
            }}
          >
            <span aria-hidden="true" style={{ flexShrink: 0, display: 'flex' }}>
              {icon}
            </span>
            {expanded && <span>{label}</span>}
          </button>
        )
      })}

      <button
        type="button"
        title={fccUp ? 'Stop fcc-server' : 'Run fcc-server'}
        onClick={() => setConfirmingRun(true)}
        disabled={runMutation.isPending}
        style={{
          ...navButtonBaseStyle,
          marginTop: 12,
          fontSize: 13.5,
          fontWeight: 800,
          background: fccUp ? 'var(--red)' : 'var(--green)',
          color: fccUp ? '#1a0b0b' : '#0c1410',
          opacity: runMutation.isPending ? 0.5 : 1,
        }}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          {fccUp ? (
            <rect x="4.5" y="4.5" width="9" height="9" rx="1.5" fill="currentColor" />
          ) : (
            <polygon points="6,4 14,9 6,14" fill="currentColor" />
          )}
        </svg>
        {expanded && <span>{fccUp ? 'Stop fcc-server' : 'Run fcc-server'}</span>}
      </button>

      <div style={{ flex: 1 }} />

      <button
        type="button"
        title="Toggle theme"
        onClick={toggleTheme}
        style={{ ...navButtonBaseStyle, fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--muted)' }}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
          <circle cx="9" cy="9" r="4" stroke="currentColor" strokeWidth="1.6" />
          <path d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        {expanded && <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>}
      </button>

      <button
        type="button"
        title="Collapse sidebar"
        onClick={() => setCollapsed((current) => !current)}
        style={{ ...navButtonBaseStyle, fontSize: 13, fontWeight: 600, background: 'transparent', color: 'var(--muted)' }}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 18 18"
          fill="none"
          aria-hidden="true"
          style={{ flexShrink: 0, transform: collapsed ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}
        >
          <path d="M11 3L5 9l6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {expanded && <span>Collapse</span>}
      </button>

      {confirmingRun && (
        <ConfirmDialog
          title={fccUp ? 'Stop fcc-server?' : 'Run fcc-server?'}
          body={
            fccUp
              ? 'In-flight requests will fail while FCC is stopped.'
              : 'This launches the fcc-server process on this machine.'
          }
          confirmLabel={fccUp ? 'Stop fcc-server' : 'Run fcc-server'}
          confirmColor={fccUp ? 'var(--red)' : 'var(--green)'}
          onConfirm={handleRunConfirm}
          onCancel={() => setConfirmingRun(false)}
        />
      )}

      {runToast && (
        <Toast title={runToast.title} body={runToast.body} onDismiss={() => setRunToast(null)} />
      )}
    </aside>
  )
}
