interface Props {
  label: string
  value: string | number
  sub?: string
  color?: 'green' | 'red' | 'cyan' | 'yellow' | 'muted' | 'orange'
}

const colorMap: Record<string, string> = {
  green: 'text-term-green',
  red: 'text-term-red',
  cyan: 'text-term-cyan',
  yellow: 'text-term-yellow',
  muted: 'text-term-muted',
  orange: 'text-term-orange',
}

export default function StatCard({ label, value, sub, color = 'cyan' }: Props) {
  return (
    <div className="bg-term-surface border border-term-border rounded p-4">
      <div className="text-[10px] text-term-muted uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-lg font-bold ${colorMap[color]}`}>{value}</div>
      {sub && <div className="text-[10px] text-term-muted mt-1">{sub}</div>}
    </div>
  )
}
