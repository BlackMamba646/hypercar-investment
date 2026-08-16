interface Props {
  text: string
  variant?: 'green' | 'red' | 'yellow' | 'cyan' | 'purple' | 'muted' | 'orange'
}

const styles: Record<string, string> = {
  green: 'bg-term-green/10 text-term-green border-term-green/30',
  red: 'bg-term-red/10 text-term-red border-term-red/30',
  yellow: 'bg-term-yellow/10 text-term-yellow border-term-yellow/30',
  cyan: 'bg-term-cyan/10 text-term-cyan border-term-cyan/30',
  purple: 'bg-term-purple/10 text-term-purple border-term-purple/30',
  orange: 'bg-term-orange/10 text-term-orange border-term-orange/30',
  muted: 'bg-term-muted/10 text-term-muted border-term-muted/30',
}

export default function Badge({ text, variant = 'muted' }: Props) {
  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-medium rounded border ${styles[variant]}`}>
      {text}
    </span>
  )
}
