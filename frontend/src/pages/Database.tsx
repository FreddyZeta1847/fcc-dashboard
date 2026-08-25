/*
 * Database.tsx
 * Read-only raw SQLite table browser — a debugging aid for the other three
 * pages, not a query builder. Lists the real table names from
 * useDbTables(), lets the user pick one, and renders its rows via
 * useDbTableRows(selectedTable, 50, 0). Pagination controls are out of
 * scope for this task (fixed limit/offset); a future refinement can add
 * them without touching this rendering approach.
 *
 * The row table is built by zipping `columns[i]` with each `row[i]` by
 * INDEX, never by a hardcoded column name or count — `rows` arrives as
 * `unknown[][]`, a genuinely generic dump of whatever the real table
 * schema is. This is deliberate: a future phase can add a table with an
 * entirely different shape and this component keeps working unchanged.
 *
 * `data.total` (the real row count) is rendered alongside the fetched
 * rows: with a fixed limit=50 and no pagination, silently showing 50
 * oldest-first rows on a table with thousands more would be misleading,
 * not just "not yet paginated" — the count line is what tells the user
 * the view is truncated.
 */
import { useState } from 'react'
import { useDbTables, useDbTableRows } from '../hooks/useDbTables'

const ROW_LIMIT = 50
const ROW_OFFSET = 0

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return String(value)
}

function TableRowsView({ table }: { table: string }) {
  const { data, isLoading, isError } = useDbTableRows(table, ROW_LIMIT, ROW_OFFSET)

  if (isError) {
    return <p className="text-sm text-red-600">Couldn't load rows for "{table}".</p>
  }
  if (isLoading || !data) {
    return <p className="text-sm text-gray-500">Loading rows…</p>
  }
  if (data.rows.length === 0) {
    return <p className="text-sm text-gray-500">No rows.</p>
  }

  return (
    <div>
      <p className="mb-2 text-sm text-gray-500">
        Showing {data.rows.length} of {data.total} rows (oldest first).
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-gray-300 text-left">
              {data.columns.map((column) => (
                <th key={column} className="px-3 py-2 text-xs font-medium text-gray-500">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              // Raw SQLite dump rows carry no stable id of their own — index
              // is the only key available, and this list is never reordered.
              // eslint-disable-next-line react/no-array-index-key
              <tr key={rowIndex} className="border-b border-gray-200">
                {data.columns.map((column, columnIndex) => (
                  <td key={column} className="px-3 py-2 text-sm text-gray-700">
                    {formatCell(row[columnIndex])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Database() {
  const { data, isLoading, isError } = useDbTables()
  const [selectedTable, setSelectedTable] = useState('')

  if (isError) {
    return <div className="p-4 text-red-600">Couldn't load the table list.</div>
  }
  if (isLoading || !data) {
    return <div className="p-4">Loading tables…</div>
  }

  return (
    <div className="flex gap-4 p-4">
      <nav className="w-48 shrink-0">
        <h2 className="text-sm font-medium text-gray-500">Tables</h2>
        <ul>
          {data.tables.map((table) => (
            <li key={table}>
              <button
                type="button"
                onClick={() => setSelectedTable(table)}
                className={`block w-full px-2 py-1 text-left text-sm ${
                  table === selectedTable ? 'font-semibold text-gray-900' : 'text-gray-700'
                }`}
              >
                {table}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <section className="flex-1">
        {selectedTable === '' ? (
          <p className="text-sm text-gray-500">Select a table to view its rows.</p>
        ) : (
          <TableRowsView table={selectedTable} />
        )}
      </section>
    </div>
  )
}
