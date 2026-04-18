'use client'

import { useEffect, useState } from 'react'
import { getSignals } from '@/lib/api'
import { useAgentStream } from '@/lib/useAgentStream'
import type { CompanySignal, SignalType } from '@/lib/types'
import PanelActivityFeed from './PanelActivityFeed'

const TYPE_BADGE: Record<SignalType, string> = {
  funding: 'bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/30',
  hiring: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
  engagement: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30',
}

const TYPE_ICON: Record<SignalType, string> = {
  funding: '💰',
  hiring: '💼',
  engagement: '👀',
}

const STATUS_BADGE: Record<string, string> = {
  new: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  resolved: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
  contacted: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  skipped: 'bg-neutral-800 text-neutral-500 border-neutral-700',
}

export default function SignalsStream({ campaignId }: { campaignId: string }) {
  const [signals, setSignals] = useState<CompanySignal[]>([])
  const { events, loaded } = useAgentStream(campaignId)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    const load = async () => {
      try {
        const data = await getSignals(campaignId)
        if (!cancelled) setSignals(data)
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
          <h2 className="text-[15px] font-medium text-neutral-100">Radar</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Funding rounds, hiring spikes &amp; competitor engagement
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] text-fuchsia-200 border border-fuchsia-500/30 bg-fuchsia-500/10 rounded-full px-2 py-0.5 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-fuchsia-400 animate-pulse" />
          Apify · multi-actor
        </span>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto pr-1 flex-1 min-h-0">
        {signals.length === 0 && (
          <PanelActivityFeed
            events={events}
            streams={['signals', 'system']}
            loaded={loaded}
            emptyLabel="› watching for funding rounds, hiring spikes, competitor engagement…"
          />
        )}
        {signals.map((sig) => {
          const type = (sig.type ?? 'funding') as SignalType
          const typeBadge = TYPE_BADGE[type] || TYPE_BADGE.funding
          const statusBadge = STATUS_BADGE[sig.status] || STATUS_BADGE.new
          return (
            <div
              key={sig.id}
              className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 hover:border-neutral-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${typeBadge}`}
                    >
                      {TYPE_ICON[type]} {type}
                    </span>
                    <p className="text-sm font-medium text-neutral-200 truncate">
                      {sig.company_name || 'Unknown company'}
                    </p>
                  </div>
                  <p className="text-[12px] text-neutral-300 mt-1 leading-snug line-clamp-3">
                    {sig.signal_text}
                  </p>
                  {sig.suggested_role && (
                    <p className="text-[10px] font-mono text-neutral-500 mt-1">
                      → DM target: {sig.suggested_role}
                    </p>
                  )}
                  {sig.signal_url && (
                    <a
                      href={sig.signal_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 mt-1 inline-block truncate max-w-full"
                    >
                      ↗ source
                    </a>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span
                    className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}
                  >
                    {sig.status}
                  </span>
                </div>
              </div>

              {sig.resolved_lead_url && sig.status === 'contacted' && (
                <div className="mt-2 rounded-md bg-emerald-950/30 border border-emerald-900/40 px-2.5 py-1.5">
                  <p className="text-[10px] font-mono uppercase text-emerald-400/80">
                    DM sent →{' '}
                    <a
                      href={sig.resolved_lead_url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      {sig.resolved_lead_url.replace(
                        'https://www.linkedin.com',
                        '',
                      )}
                    </a>
                  </p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
