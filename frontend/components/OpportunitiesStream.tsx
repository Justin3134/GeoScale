'use client'

import { useEffect, useState } from 'react'
import { getOpportunities } from '@/lib/api'
import { useAgentStream } from '@/lib/useAgentStream'
import type { Opportunity } from '@/lib/types'
import PanelActivityFeed from './PanelActivityFeed'

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

export default function OpportunitiesStream({
  campaignId,
}: {
  campaignId: string
}) {
  const [opps, setOpps] = useState<Opportunity[]>([])
  const { events, loaded } = useAgentStream(campaignId)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    const load = async () => {
      try {
        const data = await getOpportunities(campaignId)
        if (!cancelled) setOpps(data)
      } catch {
        // ignore
      }
    }
    load()
    const interval = setInterval(load, 8_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [campaignId])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-start justify-between mb-3 gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-medium text-neutral-100">Opportunities</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Press, VC programs, hackathons &amp; accelerators to pitch
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-neutral-300 border border-neutral-800 bg-neutral-900/60 rounded-full px-2 py-0.5 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Apify
        </span>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto pr-1 flex-1 min-h-0">
        <PanelActivityFeed
          campaignId={campaignId}
          events={events}
          streams={['opportunities', 'system']}
          loaded={loaded}
          emptyLabel="› sweeping for hackathons, press, accelerators…"
          cap={opps.length > 0 ? 6 : 60}
        />
        {opps.length > 0 && (
          <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
            Opportunities found
          </p>
        )}
        {opps.map((opp) => {
          const typeBadge = TYPE_BADGE[opp.type] || TYPE_BADGE.event
          const statusBadge =
            STATUS_BADGE[opp.status] || STATUS_BADGE.identified
          return (
            <div
              key={opp.id}
              className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 hover:border-neutral-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${typeBadge}`}
                    >
                      {opp.type}
                    </span>
                    <p className="text-sm font-medium text-neutral-200 truncate">
                      {opp.title}
                    </p>
                  </div>
                  {opp.description && (
                    <p className="text-[11px] text-neutral-500 mt-1 line-clamp-2">
                      {opp.description}
                    </p>
                  )}
                  {opp.url && (
                    <a
                      href={opp.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 mt-1 inline-block truncate max-w-full"
                    >
                      ↗ {opp.url}
                    </a>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-[11px] font-mono text-neutral-400 tabular-nums">
                    {opp.score}/10
                  </span>
                  <span
                    className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}
                  >
                    {opp.status}
                  </span>
                </div>
              </div>

              {opp.pitch_text && opp.status !== 'identified' && (
                <div className="mt-2 rounded-md bg-emerald-950/30 border border-emerald-900/40 px-2.5 py-1.5">
                  <p className="text-[10px] font-mono uppercase text-emerald-400/80 mb-1">
                    pitch sent {opp.pitch_language ? `· ${opp.pitch_language}` : ''}
                  </p>
                  <p className="text-[12px] text-emerald-100/90 leading-snug whitespace-pre-wrap line-clamp-6">
                    {opp.pitch_text}
                  </p>
                </div>
              )}

              {opp.contact_email && (
                <p className="mt-2 text-[10px] font-mono text-neutral-500">
                  contact: {opp.contact_email}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
