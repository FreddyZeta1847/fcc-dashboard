/*
 * processControlMessages.ts
 * Human-readable copy for every outcome `POST /control/start`/`/stop` can
 * return — all of them normal 200 responses, never HTTP errors (see
 * BACKEND--api / BACKEND--process-control). Shared between
 * ProcessControls.tsx (Settings page) and Sidebar.tsx's "Run fcc-server"
 * quick action, both of which trigger the same start endpoint from two
 * independent UI entry points and want identical wording for the same
 * result. Kept in its own module (not exported from a component file) so
 * Vite's Fast Refresh isn't disabled for either component file.
 */
import type { ControlStartAction, ControlStopAction } from '../api/types'

export function startMessage(action: ControlStartAction): string {
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

export function stopMessage(action: ControlStopAction): string {
  switch (action) {
    case 'stopped':
      return 'FCC stopped.'
    case 'not_running':
      return 'FCC was not running.'
    case 'stop_failed':
      return 'FCC failed to stop.'
  }
}
