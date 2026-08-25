/*
 * Overview.tsx
 * The dashboard's landing page. Pure composition — mounts StatusPanel
 * (Task 3), MoneySavedHeadline (Task 4), and RecentRequestsFeed (Task 5)
 * together. Each panel is self-fetching (owns its own query), so this
 * component adds no data-fetching logic of its own; it only lays the
 * three out. Mounted by App once the backend-unreachable gate (Task 3)
 * passes.
 */
import { StatusPanel } from '../components/StatusPanel'
import { MoneySavedHeadline } from '../components/MoneySavedHeadline'
import { RecentRequestsFeed } from '../components/RecentRequestsFeed'

export function Overview() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <MoneySavedHeadline />
      <StatusPanel />
      <RecentRequestsFeed />
    </div>
  )
}
