'use client'

import { useEffect, useMemo, useState } from 'react'
import { notFound, useParams } from 'next/navigation'
import Link from 'next/link'
import LeadDetailCard from '@/components/LeadDetailCard'
import { getCampaign, getLeads } from '@/lib/api'
import type { Campaign, Lead } from '@/lib/types'

type BucketSlug =
  | 'people'
  | 'contacted'

interface BucketConfig {
  title: string
  leadFilter?: (l: Lead) => boolean
  emptyLabel: string
  statuses: string
}

const BUCKETS: Record<BucketSlug, BucketConfig> = {
  people: {
    title: 'People found',
    leadFilter: () => true,
    emptyLabel: '› no people found yet — agent is still scanning…',
    statuses: 'all statuses',
  },
  contacted: {
    title: 'People contacted',
    leadFilter: (l) =>
      l.status === 'contacted' || l.status === 'replied' || l.status === 'meeting',
    emptyLabel: '› no outreach sent yet — agent is still drafting…',
    statuses: 'contacted · replied · meeting',
  },
}

const VALID: BucketSlug[] = ['people', 'contacted']

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
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false

    const load = async () => {
      try {
        await Promise.all([
          getCampaign(campaignId).then((c) => { if (!cancelled) setCampaign(c) }),
          getLeads(campaignId).then((d) => { if (!cancelled) setLeads(d) }),
        ])
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
  }, [campaignId])

  const filteredLeads = useMemo(
    () => (cfg.leadFilter ? leads.filter(cfg.leadFilter) : []),
    [leads, cfg],
  )

  const count = filteredLeads.length

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

          {filteredLeads.map((lead, i) => (
            <LeadDetailCard
              key={`${lead.source_post_url || lead.linkedin_url || lead.name}-${i}`}
              lead={lead}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
