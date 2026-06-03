import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useMemo } from 'react'

export default function DataTable({ columns, rows, hidden, onUrlClick }) {
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

  return (
    <div className="table-wrap">
      <table>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id}>
              {r.getVisibleCells().map((c) => (
                <td key={c.id}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p style={{ padding: '1rem' }}>No rows yet. Upload a CSV to begin.</p>
      )}
    </div>
  )
}
