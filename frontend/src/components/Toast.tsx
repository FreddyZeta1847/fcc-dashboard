/*
 * Toast.tsx
 * Shared bottom-right dismissible notification, used for process-control
 * outcomes (see ProcessControls.tsx) so a start/stop result stays visible
 * as a small aside rather than only living inline in the panel that
 * triggered it. `role="status"` (not "alert") since these are calm,
 * expected outcomes — including "FCC isn't installed," a normal 200
 * response, not an error — never an interruptive announcement.
 */
interface ToastProps {
  title: string
  body: string
  onDismiss: () => void
}

export function Toast({ title, body, onDismiss }: ToastProps) {
  return (
    <div
      role="status"
      style={{
        position: 'fixed',
        right: 24,
        bottom: 24,
        zIndex: 60,
        width: 350,
        maxWidth: 'calc(100vw - 48px)',
        background: 'var(--panel)',
        border: '1px solid var(--border2)',
        borderRadius: 14,
        padding: '16px 18px',
        boxShadow: '0 16px 40px rgba(0,0,0,.4)',
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
      }}
    >
      <span
        aria-hidden="true"
        style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--blue)', marginTop: 6, flexShrink: 0 }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800 }}>{title}</div>
        <div style={{ fontSize: 13, color: 'var(--muted)' }}>{body}</div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        title="Dismiss"
        style={{
          font: 'inherit',
          fontSize: 15,
          fontWeight: 700,
          border: 'none',
          background: 'transparent',
          color: 'var(--faint)',
          cursor: 'pointer',
          padding: '0 2px',
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  )
}
