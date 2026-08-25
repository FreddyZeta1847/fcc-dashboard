/*
 * Nav.tsx
 * Tab navigation bar for the dashboard's four pages (Overview, Usage,
 * Settings, Database). Stateless and controlled: App.tsx owns which tab
 * is active (local useState) and passes it down, so the "backend
 * unreachable" resilience gate in App.tsx can keep short-circuiting the
 * whole app regardless of nav state. Exports the `Tab` union type so
 * App.tsx and later pages/tests share one definition instead of each
 * redeclaring it.
 */
export type Tab = 'overview' | 'usage' | 'settings' | 'database'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'usage', label: 'Usage' },
  { id: 'settings', label: 'Settings' },
  { id: 'database', label: 'Database' },
]

interface NavProps {
  activeTab: Tab
  onTabChange: (tab: Tab) => void
}

export function Nav({ activeTab, onTabChange }: NavProps) {
  return (
    <nav className="flex gap-2 border-b border-gray-200 px-4">
      {TABS.map(({ id, label }) => {
        const isActive = id === activeTab
        return (
          <button
            key={id}
            type="button"
            onClick={() => onTabChange(id)}
            className={
              isActive
                ? 'px-3 py-2 border-b-2 border-blue-600 text-blue-600 font-semibold'
                : 'px-3 py-2 border-b-2 border-transparent text-gray-500 hover:text-gray-700'
            }
          >
            {label}
          </button>
        )
      })}
    </nav>
  )
}
