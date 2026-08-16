interface Column<T> {
  key: string
  header: string
  render?: (row: T) => React.ReactNode
  className?: string
}

interface Props<T> {
  columns: Column<T>[]
  data: T[]
  onRowClick?: (row: T) => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function DataTable<T = any>({ columns, data, onRowClick }: Props<T>) {
  return (
    <div className="overflow-x-auto border border-term-border rounded">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-term-border bg-term-surface">
            {columns.map(col => (
              <th key={col.key} className={`px-3 py-2 text-left text-term-muted font-medium uppercase tracking-wider text-[10px] ${col.className || ''}`}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-term-muted">
                No data available
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick?.(row)}
                className={`border-b border-term-border transition-colors ${
                  onRowClick ? 'cursor-pointer hover:bg-term-hover' : ''
                } ${i % 2 === 0 ? '' : 'bg-term-surface/30'}`}
              >
                {columns.map(col => (
                  <td key={col.key} className={`px-3 py-2 ${col.className || ''}`}>
                    {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
