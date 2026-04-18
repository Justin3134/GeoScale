import Link from 'next/link'

interface Props {
  href: string
  label: string
  value: number
}

export default function StatCardLink({ href, label, value }: Props) {
  return (
    <Link
      href={href}
      className="group relative bg-neutral-900/60 border border-neutral-800 rounded-xl p-3 backdrop-blur-sm hover:border-neutral-700 hover:bg-neutral-900/80 cursor-pointer transition-colors block"
    >
      <span className="absolute top-2 right-2 text-[11px] font-mono text-neutral-500 opacity-0 group-hover:opacity-70 transition-opacity">
        →
      </span>
      <div className="text-2xl font-medium text-neutral-100 tracking-tight tabular-nums">
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-[0.14em] text-neutral-500 mt-1 font-mono">
        {label}
      </div>
    </Link>
  )
}
