import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useMemo } from 'react'

function sortIndicator(columnId, sort) {
  if (!sort || sort.sortBy !== columnId) {
    return ''
  }
  return sort.sortDir === 'asc' ? ' ↑' : ' ↓'
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
}) {
  const visibleColumns = useMemo(
    () => columns.filter((c) => !hidden.includes(c)),
    [columns, hidden]
  )

  const tableColumns = useMemo(
    () =>
      visibleColumns.map((col) => ({
        accessorFn: (row) => row.data[col],
        id: col,
        header: col,
        cell: (ctx) => {
          if (col === 'url') {
            const row = ctx.row.original
            const cls = row.clicked ? 'btn btn-green' : 'btn btn-blue'
            return (
              <button className={cls} onClick={() => onUrlClick(row)}>
                {row.clicked ? 'Visited' : 'Open'}
              </button>
            )
          }
          return ctx.getValue()
        },
      })),
    [visibleColumns, onUrlClick]
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

  return (
    <div className="table-wrap">
      <table>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              <th className="row-select-cell">
                <input
                  aria-label="Select all rows on page"
                  type="checkbox"
                  checked={allSelected}
                  disabled={rows.length === 0}
                  onChange={onToggleAllRows}
                />
              </th>
              {hg.headers.map((h) => (
                <th key={h.id}>
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
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => {
            const original = r.original
            return (
              <tr key={r.id} className={selectedRowIds?.has(original.id) ? 'selected-row' : ''}>
                <td className="row-select-cell">
                  <input
                    aria-label={`Select row ${original.id}`}
                    type="checkbox"
                    checked={selectedRowIds?.has(original.id) || false}
                    onChange={() => onToggleRowSelection(original.id)}
                  />
                </td>
                {r.getVisibleCells().map((c) => (
                  <td key={c.id}>
                    {flexRender(c.column.columnDef.cell, c.getContext())}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p style={{ padding: '1rem' }}>No rows yet. Upload a CSV to begin.</p>
      )}
    </div>
  )
}
