/*
 * Settings.tsx
 * The dashboard's Settings page. Pure composition — mounts PricingEditor
 * (Task 4), PriceRefreshFlow (Task 5), and ProcessControls (Task 6)
 * together. Each is self-fetching (owns its own query/mutation hooks), so
 * this component adds no data-fetching logic of its own; it only lays the
 * three out. Process controls are grouped visually apart (a divider) from
 * the two pricing tools since starting/stopping the FCC process is an
 * unrelated action from editing prices — not a functional requirement,
 * just a readability choice. Mounted by App for the `settings` tab.
 */
import { PricingEditor } from '../components/PricingEditor'
import { PriceRefreshFlow } from '../components/PriceRefreshFlow'
import { ProcessControls } from '../components/ProcessControls'

export function Settings() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <PricingEditor />
      <PriceRefreshFlow />
      <hr className="border-gray-200" />
      <ProcessControls />
    </div>
  )
}
