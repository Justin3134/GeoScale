'use client'

import { useEffect, useState } from 'react'
import { getLeads } from '@/lib/api'
import { useAgentStream } from '@/lib/useAgentStream'
import type { Lead } from '@/lib/types'
import PanelActivityFeed from './PanelActivityFeed'

const PLATFORM_BADGE: Record<string, string> = {
  linkedin: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  reddit: 'bg-orange-500/10 text-orange-300 border-orange-500/30',
  youtube: 'bg-red-600/10 text-red-400 border-red-600/30',
  naver: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  quora: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
  zhihu: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  weibo: 'bg-red-500/10 text-red-300 border-red-500/30',
  xiaohongshu: 'bg-pink-500/10 text-pink-300 border-pink-500/30',
}

const STATUS_BADGE: Record<string, string> = {
  identified: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  contacted: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  replied: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  meeting: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
}

export default function PeopleStream({ campaignId }: { campaignId: string }) {
  const [leads, setLeads] = useState<Lead[]>([])
  const { events, loaded } = useAgentStream(campaignId)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    const load = async () => {
      try {
        const data = await getLeads(campaignId)
        if (!cancelled) setLeads(data)
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
          <h2 className="text-[15px] font-medium text-neutral-100">People</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            Buyers venting about this pain on social
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
          streams={['people', 'system']}
          loaded={loaded}
          emptyLabel="› scanning for people venting about this pain…"
          cap={leads.length > 0 ? 6 : 60}
        />
        {leads.length > 0 && (
          <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
            People found
          </p>
        )}
        {leads.map((lead, i) => {
          const platform = (lead.platform || 'linkedin').toLowerCase()
          const platformBadge =
            PLATFORM_BADGE[platform] || PLATFORM_BADGE.linkedin
          const statusBadge = STATUS_BADGE[lead.status] || STATUS_BADGE.identified
          return (
            <div
              key={`${lead.source_post_url || lead.name}-${i}`}
              className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 hover:border-neutral-700 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${platformBadge}`}
                    >
                      {platform}
                    </span>
                    <p className="text-sm font-medium text-neutral-200 truncate">
                      {lead.name}
                    </p>
                  </div>
                  {(lead.title || lead.company) && (
                    <p className="text-[11px] text-neutral-500 mt-1 truncate">
                      {lead.title}
                      {lead.title && lead.company ? ' · ' : ''}
                      {lead.company}
                    </p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-[11px] font-mono text-neutral-400 tabular-nums">
                    {lead.score}/10
                  </span>
                  <span
                    className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}
                  >
                    {lead.status}
                  </span>
                </div>
              </div>

              {lead.source_comment_text && (
                <div className="mt-2 rounded-md bg-neutral-900/60 border border-neutral-800 px-2.5 py-1.5">
                  <p className="text-[10px] font-mono uppercase text-neutral-600 mb-1">
                    they said
                  </p>
                  <p className="text-[12px] text-neutral-300 leading-snug line-clamp-3">
                    {lead.source_comment_text}
                  </p>
                  {lead.source_post_url && (
                    <a
                      href={lead.source_post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 mt-1 inline-block truncate max-w-full"
                    >
                      ↗ {lead.source_post_url}
                    </a>
                  )}
                </div>
              )}

              {lead.reply_text && (
                <div className="mt-2 rounded-md bg-emerald-950/30 border border-emerald-900/40 px-2.5 py-1.5">
                  <p className="text-[10px] font-mono uppercase text-emerald-400/80 mb-1">
                    we replied {lead.reply_language ? `· ${lead.reply_language}` : ''}
                  </p>
                  <p className="text-[12px] text-emerald-100/90 leading-snug whitespace-pre-wrap">
                    {lead.reply_text}
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
