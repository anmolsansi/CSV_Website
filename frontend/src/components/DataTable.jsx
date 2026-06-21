import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useMemo, useRef } from 'react'

function sortIndicator(columnId, sort) {
  if (!sort || sort.sortBy !== columnId) {
    return ''
  }
  return sort.sortDir === 'asc' ? ' ↑' : ' ↓'
}

function StatusBadge({ status }) {
  if (!status) return null
  return <span className={`app-status-badge ${status}`}>{status.replace('_', ' ')}</span>
}

function PriorityScore({ score, triage }) {
  if (score == null) return null
  let cls = 'priority-none'
  if (score >= 80) cls = 'priority-high'
  else if (score >= 50) cls = 'priority-medium'
  else if (score > 0) cls = 'priority-low'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span className={`priority-score ${cls}`}>{score}</span>
      {triage && <span className={`triage-badge triage-${triage}`}>{triage.replace('_', ' ')}</span>}
    </div>
  )
}

export default function DataTable({
  columns,
  rows,
  hidden,
  sort,
  selectedRowIds,
  onToggleRowSelection,
  onToggleAllRows,
  onSortChange,
  onUrlClick,
  onRowClick,
  pinnedColumns = [],
  density = 'comfortable',
}) {
  const parentRef = useRef(null)

  const visibleColumns = useMemo(
    () => columns.filter((c) => !hidden.includes(c)),
    [columns, hidden]
  )

  const tableColumns = useMemo(
    () => [
      ...visibleColumns.map((col) => ({
        accessorFn: (row) => row.data[col],
        id: col,
        header: col,
        cell: (ctx) => {
          if (col === 'url') {
            const row = ctx.row.original
            const cls = row.clicked ? 'btn btn-green' : 'btn btn-blue'
            return (
              <button className={cls} onClick={(e) => { e.stopPropagation(); onUrlClick(row) }}>
                {row.clicked ? 'Visited' : 'Open'}
              </button>
            )
          }
          return ctx.getValue()
        },
        meta: { pinned: pinnedColumns.includes(col) ? 'left' : undefined },
      })),
      {
        id: '_priority',
        header: 'Priority',
        accessorFn: (row) => row.priority_score,
        cell: (ctx) => {
          const row = ctx.row.original
          return <PriorityScore score={row.priority_score} triage={row.triage} />
        },
      },
      {
        id: '_app_status',
        header: 'App Status',
        accessorFn: (row) => row.app_status,
        cell: (ctx) => {
          const row = ctx.row.original
          if (!row.app_status && !row.app_id) return null
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <StatusBadge status={row.app_status} />
              {row.follow_up_at && <span className="follow-up-badge">Follow-up</span>}
            </div>
          )
        },
      },
    ],
    [visibleColumns, onUrlClick, pinnedColumns]
  )

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  })

  const selectedCount = selectedRowIds?.size || 0
  const allSelected = rows.length > 0 && selectedCount === rows.length

  const handleHeaderClick = (columnId) => {
    if (!onSortChange) {
      return
    }
    const nextDirection =
      sort?.sortBy === columnId && sort?.sortDir === 'asc' ? 'desc' : 'asc'
    onSortChange(columnId, nextDirection)
  }

  const densityClass = density === 'compact' ? 'density-compact' : density === 'dense' ? 'density-dense' : ''

  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => density === 'dense' ? 32 : density === 'compact' ? 40 : 52,
    overscan: 10,
  })

  return (
    <div className={`table-wrap ${densityClass}`}>
      <table role="table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} role="row">
              <th className="row-select-cell" scope="col">
                <input
                  aria-label="Select all rows on page"
                  type="checkbox"
                  checked={allSelected}
                  disabled={rows.length === 0}
                  onChange={onToggleAllRows}
                />
              </th>
              {hg.headers.map((h) => {
                const isPinned = pinnedColumns.includes(h.column.id)
                const isSorted = sort?.sortBy === h.column.id
                return (
                  <th
                    key={h.id}
                    scope="col"
                    className={isPinned ? 'pin-left' : ''}
                    aria-sort={isSorted ? (sort.sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  >
                    <button
                      className="table-header-button"
                      type="button"
                      onClick={() => handleHeaderClick(h.column.id)}
                      title={`Sort by ${h.column.id}`}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sortIndicator(h.column.id, sort)}
                    </button>
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody ref={parentRef} style={{ overflow: 'auto', position: 'relative', maxHeight: '70vh' }}>
          <tr>
            <td colSpan={visibleColumns.length + 2} style={{ height: `${rowVirtualizer.getTotalSize()}px`, padding: 0, border: 'none' }} />
          </tr>
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const r = table.getRowModel().rows[virtualRow.index]
            if (!r) return null
            const original = r.original
            return (
              <tr
                key={r.id}
                role="row"
                className={selectedRowIds?.has(original.id) ? 'selected-row' : ''}
                onClick={() => onRowClick?.(original)}
                style={{
                  cursor: onRowClick ? 'pointer' : 'default',
                  position: 'absolute',
                  transform: `translateY(${virtualRow.start}px)`,
                  width: '100%',
                }}
              >
                <td className="row-select-cell" role="cell">
                  <input
                    aria-label={`Select row ${original.id}`}
                    type="checkbox"
                    checked={selectedRowIds?.has(original.id) || false}
                    onChange={() => onToggleRowSelection(original.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </td>
                {r.getVisibleCells().map((c) => {
                  const isPinned = pinnedColumns.includes(c.column.id)
                  return (
                    <td key={c.id} role="cell" className={isPinned ? 'pin-left' : ''}>
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="empty-state">
          <h3>No rows found</h3>
          <p>No results match your current filters. Try adjusting your search criteria.</p>
        </div>
      )}
    </div>
  )
}
