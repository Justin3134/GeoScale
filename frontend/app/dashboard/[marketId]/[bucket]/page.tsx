'use client'

import { useEffect, useMemo, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import Link from 'next/link'
import LeadDetailCard from '@/components/LeadDetailCard'
import OpportunityDetailCard from '@/components/OpportunityDetailCard'
import { getCampaign, getLeads, getOpportunities } from '@/lib/api'
import type { Campaign, Lead, Opportunity } from '@/lib/types'

type BucketSlug =
  | 'people'
  | 'contacted'
  | 'replied'
  | 'opportunities'
  | 'pitches'
  | 'meetings'

interface BucketConfig {
  title: string
  source: 'leads' | 'opportunities'
  leadFilter?: (l: Lead) => boolean
  oppFilter?: (o: Opportunity) => boolean
  emptyLabel: string
  statuses: string
}

const BUCKETS: Record<BucketSlug, BucketConfig> = {
  people: {
    title: 'People found',
    source: 'leads',
    leadFilter: () => true,
    emptyLabel: '› no people found yet — agent is still scanning…',
    statuses: 'all statuses',
  },
  contacted: {
    title: 'People contacted',
    source: 'leads',
    leadFilter: (l) =>
      l.status === 'contacted' || l.status === 'replied' || l.status === 'meeting',
    emptyLabel: '› no outreach sent yet — agent is still drafting…',
    statuses: 'contacted · replied · meeting',
  },
  replied: {
    title: 'Replied',
    source: 'leads',
    leadFilter: (l) => l.status === 'replied' || l.status === 'meeting',
    emptyLabel: '› no replies yet — agent is waiting on inboxes…',
    statuses: 'replied · meeting',
  },
  opportunities: {
    title: 'Opportunities',
    source: 'opportunities',
    oppFilter: () => true,
    emptyLabel: '› no opportunities yet — agent is still sweeping…',
    statuses: 'all statuses',
  },
  pitches: {
    title: 'Pitches sent',
    source: 'opportunities',
    oppFilter: (o) =>
      o.status === 'contacted' || o.status === 'replied' || o.status === 'booked',
    emptyLabel: '› no pitches sent yet — agent is still drafting…',
    statuses: 'contacted · replied · booked',
  },
  meetings: {
    title: 'Meetings',
    source: 'leads',
    leadFilter: (l) => l.status === 'meeting',
    emptyLabel: '› no meetings booked yet…',
    statuses: 'meeting',
  },
}

const VALID: BucketSlug[] = [
  'people',
  'contacted',
  'replied',
  'opportunities',
  'pitches',
  'meetings',
]

export default function BucketPage() {
  const params = useParams<{ marketId: string; bucket: string }>()
  const campaignId = params?.marketId as string
  const bucket = params?.bucket as BucketSlug

  if (!VALID.includes(bucket)) {
    notFound()
  }

  const cfg = BUCKETS[bucket]

  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [opps, setOpps] = useState<Opportunity[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false

    const load = async () => {
      try {
        const tasks: Promise<unknown>[] = [
          getCampaign(campaignId).then((c) => { if (!cancelled) setCampaign(c) }),
        ]
        if (cfg.source === 'leads') {
          tasks.push(getLeads(campaignId).then((d) => { if (!cancelled) setLeads(d) }))
        } else {
          tasks.push(getOpportunities(campaignId).then((d) => { if (!cancelled) setOpps(d) }))
        }
        await Promise.all(tasks)
        if (!cancelled) { setLoaded(true); setError(false) }
      } catch {
        if (!cancelled) { setLoaded(true); setError(true) }
      }
    }

    load()
    const interval = setInterval(load, 8_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [campaignId, cfg.source])

  const filteredLeads = useMemo(
    () => (cfg.leadFilter ? leads.filter(cfg.leadFilter) : []),
    [leads, cfg],
  )
  const filteredOpps = useMemo(
    () => (cfg.oppFilter ? opps.filter(cfg.oppFilter) : []),
    [opps, cfg],
  )

  const count = cfg.source === 'leads' ? filteredLeads.length : filteredOpps.length

  return (
    <div className="relative min-h-screen bg-neutral-950 text-neutral-100">
      <div className="absolute inset-x-0 top-0 h-72 bg-spotlight pointer-events-none" />

      <div className="relative max-w-4xl mx-auto px-6 py-10">
        <Link
          href={`/dashboard/${campaignId}`}
          className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 hover:text-neutral-300 inline-block mb-4 font-mono transition-colors"
        >
          ← Mission control
        </Link>

        <div className="flex items-end justify-between gap-4 mb-2">
          <h1 className="text-3xl font-medium tracking-tight bg-gradient-to-b from-white to-neutral-400 bg-clip-text text-transparent">
            {cfg.title}
          </h1>
          <span className="text-[28px] font-mono text-neutral-500 tabular-nums">
            {loaded ? count : '—'}
          </span>
        </div>

        <div className="flex items-center gap-2 mb-8 flex-wrap">
          {campaign?.country && (
            <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 font-mono">
              {campaign.country}
            </span>
          )}
          <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-700 font-mono">·</span>
          <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 font-mono">
            {cfg.statuses}
          </span>
        </div>

        <div className="flex flex-col gap-4">
          {!loaded && (
            <p className="text-sm text-neutral-500 font-mono animate-pulse">› loading…</p>
          )}
          {loaded && error && (
            <div className="rounded-xl border border-red-900/40 bg-red-950/20 p-6 text-center">
              <p className="text-sm text-red-400 font-mono">› failed to load — check the backend is running</p>
            </div>
          )}
          {loaded && !error && count === 0 && (
            <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
              <p className="text-sm text-neutral-500 font-mono">{cfg.emptyLabel}</p>
            </div>
          )}

          {cfg.source === 'leads' &&
            filteredLeads.map((lead, i) => (
              <LeadDetailCard
                key={`${lead.source_post_url || lead.linkedin_url || lead.name}-${i}`}
                lead={lead}
              />
            ))}

          {cfg.source === 'opportunities' &&
            filteredOpps.map((opp) => (
              <OpportunityDetailCard key={opp.id} opp={opp} />
            ))}
        </div>
      </div>
    </div>
  )
}
