/*
 * Database.tsx
 * Read-only raw SQLite table browser — a debugging aid for the other three
 * pages, not a query builder. Lists the real table names from
 * useDbTables(), lets the user pick one (a chip-style selector), and
 * renders its rows via useDbTableRows(selectedTable, 50, 0). Pagination
 * controls are out of scope (fixed limit/offset); a future refinement can
 * add them without touching this rendering approach.
 *
 * The row table is built by zipping `columns[i]` with each `row[i]` by
 * INDEX, never by a hardcoded column name or count — `rows` arrives as
 * `unknown[][]`, a genuinely generic dump of whatever the real table
 * schema is. This is deliberate: a future phase can add a table with an
 * entirely different shape and this component keeps working unchanged.
 * The `requests` table gets two deliberate, narrowly-scoped exceptions to
 * that generic philosophy (matching the backend's own `requests`-only
 * special-casing in `routes_db.py`): it's ordered most-recent-first
 * (`occurred_at DESC`, not raw insertion order), and each row gets an
 * expand toggle that groups its ~16 flat columns into a small, readable
 * overview (model routing / tokens / cost / timing) — see
 * REQUEST_FIELD_GROUPS below. Neither applies to any other table.
 *
 * The page opens on `requests` rather than an empty "select a table"
 * prompt. That table is why this page exists -- it's the one being debugged,
 * it always exists (`db.py` creates it unconditionally), and every other
 * table here is single-row bookkeeping. The default is derived at render
 * time rather than seeded into state, so it needs no effect to sync once
 * `useDbTables()` resolves: `chosenTable` stays null until the user actually
 * picks something, and their pick wins from then on.
 *
 * `data.total` (the real row count) is rendered alongside the fetched
 * rows: with a fixed limit=50 and no pagination, silently showing 50 rows
 * on a table with thousands more would be misleading, not just "not yet
 * paginated" — the count line is what tells the user the view is
 * truncated. Each table chip also shows its own total count.
 */
import { useState } from 'react'
import { useDbTables, useDbTableRows } from '../hooks/useDbTables'
import { Card } from '../components/Card'
import { Skeleton } from '../components/Skeleton'

// Opened by default -- see the module docstring.
const DEFAULT_TABLE = 'requests'

const ROW_LIMIT = 50
const ROW_OFFSET = 0
const EXPAND_COLUMN_WIDTH = 44

// Groups the `requests` table's flat column list into a readable overview
// for the per-row expand panel. Any column not listed here (a future
// schema addition) still shows up, under a catch-all "Other" group built
// at render time — see RequestRowDetail — so this list can't silently
// hide new data.
const REQUEST_FIELD_GROUPS: { title: string; fields: string[] }[] = [
  { title: 'Identity', fields: ['request_id', 'status'] },
  { title: 'Model routing', fields: ['provider', 'gateway_model', 'downstream_model'] },
  { title: 'Tokens', fields: ['input_tokens', 'output_tokens', 'input_tokens_estimate', 'finish_reason'] },
  { title: 'Cost', fields: ['actual_cost', 'equivalent_cost', 'savings'] },
  { title: 'Timing & errors', fields: ['occurred_at', 'occurred_at_is_estimated', 'ingested_at', 'http_status', 'exc_type'] },
]

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return String(value)
}

function RequestRowDetail({ columns, row }: { columns: string[]; row: unknown[] }) {
  const valueByColumn = Object.fromEntries(columns.map((column, index) => [column, row[index]]))
  const knownFields = new Set(REQUEST_FIELD_GROUPS.flatMap((group) => group.fields))
  const otherFields = columns.filter((column) => !knownFields.has(column))
  const groups = otherFields.length > 0 ? [...REQUEST_FIELD_GROUPS, { title: 'Other', fields: otherFields }] : REQUEST_FIELD_GROUPS

  return (
    <div
      style={{
        gridColumn: '1 / -1',
        padding: '16px 20px',
        background: 'var(--card2)',
        borderBottom: '1px solid var(--border)',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 18,
      }}
    >
      {groups.map((group) => (
        <div key={group.title}>
          <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 8 }}>
            {group.title}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {group.fields.map((field) => (
              <div key={field} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12.5 }}>
                <span style={{ color: 'var(--muted)' }}>{field}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text)', textAlign: 'right', wordBreak: 'break-all' }}>
                  {formatCell(valueByColumn[field])}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function TableRowsView({ table }: { table: string }) {
  const { data, isLoading, isError } = useDbTableRows(table, ROW_LIMIT, ROW_OFFSET)
  const [expandedRowIndex, setExpandedRowIndex] = useState<number | null>(null)

  if (isError) {
    return <p style={{ fontSize: 13, color: 'var(--red)' }}>Couldn't load rows for "{table}".</p>
  }
  if (isLoading || !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Skeleton height={14} />
        <Skeleton height={14} delay={0.15} />
        <Skeleton height={14} delay={0.3} />
      </div>
    )
  }
  if (data.rows.length === 0) {
    return (
      <div style={{ padding: '44px 20px', textAlign: 'center', color: 'var(--faint)', border: '1.5px dashed var(--border2)', borderRadius: 12 }}>
        This table has no rows.
      </div>
    )
  }

  const isRequestsTable = data.table === 'requests'
  const gridTemplateColumns = isRequestsTable
    ? `repeat(${data.columns.length}, minmax(120px, 1fr)) ${EXPAND_COLUMN_WIDTH}px`
    : `repeat(${data.columns.length}, minmax(120px, 1fr))`

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 15, fontWeight: 600 }}>{data.table}</div>
        <div style={{ fontSize: 12.5, color: 'var(--faint)' }}>
          Showing {data.rows.length} of {data.total} rows ({isRequestsTable ? 'most recent first' : 'oldest first'}).
        </div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        {/*
         * One CSS Grid container for the header AND every row, sharing a
         * single `gridTemplateColumns` — not one flex row per <div> (the
         * previous approach). Each row used to be its own independent flex
         * container, so a long value in one row (e.g. a full request_id)
         * could size that row's columns differently from the header's and
         * from every other row's, since `overflow: hidden` alone doesn't
         * stop a flex item's intrinsic minimum width from growing with its
         * content — the visible symptom was header labels and cell values
         * drifting out of alignment. A shared grid template locks every
         * cell, header or row, to the exact same column tracks by
         * construction, so this can't happen regardless of content length.
         * An expanded row's detail panel is just another grid item
         * spanning every column (`gridColumn: '1 / -1'`), inserted right
         * after that row's own cells — the grid's `auto` row flow places
         * it directly underneath without needing a nested table.
         */}
        <div style={{ display: 'grid', gridTemplateColumns, minWidth: 'min-content' }}>
          {data.columns.map((column) => (
            <div
              key={column}
              style={{ padding: '7px 12px', borderBottom: '1px solid var(--border2)', fontSize: 11, fontWeight: 800, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
            >
              {column}
            </div>
          ))}
          {isRequestsTable && <div style={{ borderBottom: '1px solid var(--border2)' }} aria-hidden="true" />}

          {data.rows.map((row, rowIndex) => {
            const isExpanded = expandedRowIndex === rowIndex
            return (
              // Raw SQLite dump rows carry no stable id of their own — row
              // index is the only key available, and this list is never
              // reordered (each fetch re-renders the whole view anyway).
              // eslint-disable-next-line react/no-array-index-key
              <div key={rowIndex} style={{ display: 'contents' }}>
                {data.columns.map((column, columnIndex) => (
                  <div
                    key={column}
                    title={formatCell(row[columnIndex])}
                    style={{ padding: '8px 12px', borderBottom: isExpanded ? 'none' : '1px solid var(--border)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}
                  >
                    {formatCell(row[columnIndex])}
                  </div>
                ))}
                {isRequestsTable && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', borderBottom: isExpanded ? 'none' : '1px solid var(--border)' }}>
                    <button
                      type="button"
                      title={isExpanded ? 'Collapse' : 'Expand'}
                      aria-label={isExpanded ? 'Collapse request details' : 'Expand request details'}
                      onClick={() => setExpandedRowIndex(isExpanded ? null : rowIndex)}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 26, height: 26, border: '1px solid var(--border2)', borderRadius: 7, background: isExpanded ? 'var(--card2)' : 'transparent', cursor: 'pointer', color: 'var(--muted)' }}
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true" style={{ transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }}>
                        <path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                )}
                {isExpanded && <RequestRowDetail columns={data.columns} row={row} />}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export function Database() {
  const { data, isLoading, isError } = useDbTables()
  // null means "the user hasn't picked one yet", which is what lets the
  // derived default below apply without overriding a real choice.
  const [chosenTable, setChosenTable] = useState<string | null>(null)

  if (isError) {
    return (
      <Card accent="red">
        <p style={{ color: 'var(--red)' }}>Couldn't load the table list.</p>
      </Card>
    )
  }
  if (isLoading || !data) {
    return (
      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Skeleton height={14} />
        <Skeleton height={14} delay={0.15} />
        <Skeleton height={14} delay={0.3} />
      </Card>
    )
  }

  const fallbackTable = data.tables.includes(DEFAULT_TABLE)
    ? DEFAULT_TABLE
    : (data.tables[0] ?? '')
  const selectedTable = chosenTable ?? fallbackTable

  return (
    <div style={{ maxWidth: 1060 }}>
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.02em' }}>Database</div>
        <div style={{ color: 'var(--muted)' }}>Read-only raw data browser, for debugging</div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 14, padding: 8, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.07em', textTransform: 'uppercase', color: 'var(--faint)', padding: '0 12px' }}>
            Tables
          </div>
          {data.tables.map((table) => {
            const isActive = table === selectedTable
            return (
              <button
                key={table}
                type="button"
                onClick={() => setChosenTable(table)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  font: 'inherit',
                  fontSize: 13,
                  fontWeight: 700,
                  padding: '8px 14px',
                  border: 'none',
                  borderRadius: 9,
                  cursor: 'pointer',
                  background: isActive ? 'var(--card2)' : 'transparent',
                  color: isActive ? 'var(--text)' : 'var(--muted)',
                }}
              >
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12.5 }}>{table}</span>
              </button>
            )
          })}
        </div>
        <Card>
          {selectedTable === '' ? (
            <p style={{ color: 'var(--faint)' }}>No tables found in the database.</p>
          ) : (
            <TableRowsView table={selectedTable} />
          )}
        </Card>
      </div>
    </div>
  )
}
