/*
 * ConfirmDialog.tsx
 * Shared confirm-before-action modal. This project's FRONTEND--security
 * rule requires an explicit confirmation step before a pricing write or
 * an FCC start/stop — every caller (PricingEditor, ProcessControls, …)
 * keeps owning its own "is a confirm pending" state and only mounts this
 * component while pending. This component itself holds no state; it's a
 * pure, controlled overlay so its behavior is trivial to test in
 * isolation from any one caller's business logic.
 */
interface ConfirmDialogProps {
  title: string
  body: string
  confirmLabel: string
  confirmColor?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  confirmColor = 'var(--blue)',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(5,7,12,.62)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <div
        style={{
          width: 400,
          maxWidth: '90vw',
          background: 'var(--panel)',
          border: '1px solid var(--border2)',
          borderRadius: 18,
          padding: 28,
          boxShadow: '0 24px 60px rgba(0,0,0,.45)',
        }}
      >
        <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>{title}</div>
        <div style={{ color: 'var(--muted)', marginBottom: 22 }}>{body}</div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              font: 'inherit',
              fontSize: 13,
              fontWeight: 700,
              padding: '9px 18px',
              borderRadius: 9,
              border: '1px solid var(--border2)',
              background: 'transparent',
              color: 'var(--muted)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              font: 'inherit',
              fontSize: 13,
              fontWeight: 800,
              padding: '9px 18px',
              borderRadius: 9,
              border: 'none',
              background: confirmColor,
              color: '#0b1018',
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
