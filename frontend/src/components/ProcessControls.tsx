/*
 * ProcessControls.tsx
 * Settings page's FCC process start/stop controls (`POST /control/start`,
 * `POST /control/stop`).
 *
 * Both Start and Stop go through the same confirm-before-action pattern as
 * PricingEditor's "Save" (Task 4): the first click only flips that button
 * into a "Confirm?" state, the mutation only fires on the follow-up
 * "Confirm" click. This is deliberate for Start too, not just Stop —
 * `FRONTEND--settings` says "both" go through the confirm step, because
 * launching an unmanaged external process is itself an action worth a
 * second look (e.g. accidentally starting a second FCC instance), even
 * though it isn't destructive the way Stop is.
 *
 * Every `action` value the backend can return here — `already_running`,
 * `executable_not_found`, `launch_failed` for start; `not_running`,
 * `stop_failed` for stop — is a normal 200 response, not an HTTP error
 * (see BACKEND--api / BACKEND--process-control). `executable_not_found` in
 * particular just means FCC isn't installed on this machine yet, a normal
 * state for a new user. So none of these render with error styling; each
 * gets its own plain, specific sentence instead of a generic failure
 * message. Only an actual network/HTTP failure (mutation `isError`) gets
 * the red "couldn't reach the server" treatment.
 */
import { useState } from 'react'
import { useControlStart, useControlStop } from '../hooks/useControl'
import type { ControlStartAction, ControlStopAction } from '../api/types'

function startMessage(action: ControlStartAction): string {
  switch (action) {
    case 'started':
      return 'FCC started.'
    case 'already_running':
      return 'FCC is already running.'
    case 'executable_not_found':
      return "FCC isn't installed on this machine (executable not found)."
    case 'launch_failed':
      return 'FCC failed to launch.'
  }
}

function stopMessage(action: ControlStopAction): string {
  switch (action) {
    case 'stopped':
      return 'FCC stopped.'
    case 'not_running':
      return 'FCC was not running.'
    case 'stop_failed':
      return 'FCC failed to stop.'
  }
}

export function ProcessControls() {
  const startMutation = useControlStart()
  const stopMutation = useControlStop()

  const [pendingAction, setPendingAction] = useState<'start' | 'stop' | null>(null)

  function handleStartClick() {
    setPendingAction('start')
  }

  function handleStopClick() {
    setPendingAction('stop')
  }

  function handleCancelClick() {
    setPendingAction(null)
  }

  function handleConfirmClick() {
    if (pendingAction === 'start') {
      startMutation.mutate(undefined, { onSuccess: () => setPendingAction(null) })
    } else if (pendingAction === 'stop') {
      stopMutation.mutate(undefined, { onSuccess: () => setPendingAction(null) })
    }
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-medium text-gray-500">FCC process</h2>
      <div className="mt-2 flex gap-2">
        {pendingAction === null && (
          <>
            <button
              type="button"
              onClick={handleStartClick}
              disabled={startMutation.isPending}
              className="bg-green-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
            >
              Start
            </button>
            <button
              type="button"
              onClick={handleStopClick}
              disabled={stopMutation.isPending}
              className="bg-red-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
            >
              Stop
            </button>
          </>
        )}

        {pendingAction !== null && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-700">
              {pendingAction === 'start' ? 'Start FCC?' : 'Stop FCC?'}
            </span>
            <button
              type="button"
              onClick={handleConfirmClick}
              disabled={startMutation.isPending || stopMutation.isPending}
              className="bg-blue-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50"
            >
              Confirm
            </button>
            <button
              type="button"
              onClick={handleCancelClick}
              className="px-3 py-1 text-sm text-gray-600"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {startMutation.isError && (
        <p className="mt-2 text-sm text-red-600">Couldn't reach the server to start FCC.</p>
      )}
      {stopMutation.isError && (
        <p className="mt-2 text-sm text-red-600">Couldn't reach the server to stop FCC.</p>
      )}

      {startMutation.data && (
        <p className="mt-2 text-sm text-gray-700">{startMessage(startMutation.data.action)}</p>
      )}
      {stopMutation.data && (
        <p className="mt-2 text-sm text-gray-700">{stopMessage(stopMutation.data.action)}</p>
      )}
    </div>
  )
}
