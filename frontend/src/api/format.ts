export function usd(value: string | number | null | undefined): string {
  if (value == null || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function pct(value: string | number | null | undefined, decimals = 1): string {
  if (value == null || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`
}

export function num(value: string | number | null | undefined, decimals = 0): string {
  if (value == null || value === '') return '—'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n)) return '—'
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: decimals }).format(n)
}

export function date(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function datetime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function pnlColor(value: string | number | null | undefined): 'green' | 'red' | 'muted' {
  if (value == null) return 'muted'
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(n) || n === 0) return 'muted'
  return n > 0 ? 'green' : 'red'
}

export function scoreColor(score: number): 'green' | 'yellow' | 'red' | 'muted' {
  if (score >= 4) return 'green'
  if (score >= 2) return 'yellow'
  if (score < 0) return 'red'
  return 'muted'
}

export function severityColor(severity: string): 'red' | 'yellow' | 'cyan' {
  if (severity === 'critical') return 'red'
  if (severity === 'warning') return 'yellow'
  return 'cyan'
}

export function statusColor(status: string): 'green' | 'cyan' | 'yellow' | 'red' | 'muted' {
  switch (status) {
    case 'actionable': return 'green'
    case 'watchlist': return 'cyan'
    case 'open': return 'green'
    case 'pending_exit': return 'yellow'
    case 'exited': return 'muted'
    case 'acquired': return 'green'
    case 'passed': return 'muted'
    case 'expired': return 'red'
    default: return 'muted'
  }
}
