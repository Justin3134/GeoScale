import type { Opportunity } from '@/lib/types'

const TYPE_BADGE: Record<string, string> = {
  hackathon: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
  event: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  accelerator: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  press: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  community: 'bg-pink-500/10 text-pink-300 border-pink-500/30',
  vc: 'bg-green-500/10 text-green-300 border-green-500/30',
}

const STATUS_BADGE: Record<string, string> = {
  identified: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  contacted: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  replied: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  booked: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
}

export default function OpportunityDetailCard({
  opp,
}: {
  opp: Opportunity
}) {
  const typeBadge = TYPE_BADGE[opp.type] || TYPE_BADGE.event
  const statusBadge = STATUS_BADGE[opp.status] || STATUS_BADGE.identified

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5 backdrop-blur-sm hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span
              className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${typeBadge}`}
            >
              {opp.type}
            </span>
            <span
              className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}
            >
              {opp.status}
            </span>
          </div>
          <h2 className="text-lg font-medium text-neutral-100 tracking-tight">
            {opp.title}
          </h2>
        </div>
        <div className="text-[12px] font-mono text-neutral-400 tabular-nums shrink-0">
          {opp.score}/10
        </div>
      </div>

      {opp.description && (
        <p className="text-[13px] text-neutral-300 leading-relaxed mb-3 whitespace-pre-wrap">
          {opp.description}
        </p>
      )}

      <div className="flex flex-wrap gap-3 mb-3">
        {opp.url && (
          <a
            href={opp.url}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-mono text-sky-400 hover:text-sky-300 transition-colors truncate max-w-full"
          >
            ↗ {opp.url}
          </a>
        )}
      </div>

      {opp.pitch_text && (opp.contact_url || opp.contact_email) && (
        <div className="flex flex-wrap items-center gap-2 mb-3 px-2.5 py-1.5 rounded-md bg-blue-950/30 border border-blue-900/40">
          <span className="text-[10px] font-mono uppercase text-blue-400/80 shrink-0">contacted via</span>
          {opp.contact_email ? (
            <a
              href={`mailto:${opp.contact_email}`}
              className="text-[11px] font-mono text-blue-300 hover:text-blue-200 transition-colors"
            >
              ✉ {opp.contact_email}
            </a>
          ) : opp.contact_url && opp.contact_url !== opp.url ? (
            <a
              href={opp.contact_url}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-mono text-blue-300 hover:text-blue-200 transition-colors truncate"
            >
              ↗ {opp.contact_url}
            </a>
          ) : (
            <a
              href={opp.contact_url ?? opp.url}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-mono text-blue-300 hover:text-blue-200 transition-colors truncate"
            >
              ↗ contact page
            </a>
          )}
        </div>
      )}

      {opp.pitch_text && opp.status !== 'identified' && (
        <div className="rounded-lg bg-emerald-950/30 border border-emerald-900/40 px-3 py-2.5">
          <p className="text-[10px] font-mono uppercase text-emerald-400/80 mb-1.5">
            pitch sent {opp.pitch_language ? `· ${opp.pitch_language}` : ''}
          </p>
          <p className="text-[13px] text-emerald-100/90 leading-relaxed whitespace-pre-wrap">
            {opp.pitch_text}
          </p>
        </div>
      )}
    </div>
  )
}
