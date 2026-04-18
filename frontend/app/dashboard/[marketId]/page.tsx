'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import BrowserScreen from '@/components/BrowserScreen'
import OpportunitiesStream from '@/components/OpportunitiesStream'
import PeopleStream from '@/components/PeopleStream'
import StatCardLink from '@/components/StatCardLink'
import { getCampaign, getStats, pauseCampaign, updateCampaignSettings } from '@/lib/api'
import type { Campaign, Stats } from '@/lib/types'

export default function DashboardPage() {
  const params = useParams<{ marketId: string }>()
  const campaignId = params?.marketId as string

  const [stats, setStats] = useState<Stats | null>(null)
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [busyPause, setBusyPause] = useState(false)
  const [busyApprovalToggle, setBusyApprovalToggle] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false

    const load = async () => {
      try {
        const [s, c] = await Promise.all([
          getStats(campaignId),
          getCampaign(campaignId),
        ])
        if (cancelled) return
        setStats(s)
        setCampaign(c)
      } catch {
        // ignore
      }
    }

    load()
    const interval = setInterval(load, 10_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [campaignId])

  const handlePause = async () => {
    if (!campaign || campaign.status !== 'running') return
    setBusyPause(true)
    try {
      await pauseCampaign(campaignId)
      setCampaign((c) => (c ? { ...c, status: 'paused' } : c))
    } finally {
      setBusyPause(false)
    }
  }

  const handleToggleApproval = async () => {
    if (!campaign) return
    setBusyApprovalToggle(true)
    const next = !campaign.require_human_approval
    try {
      await updateCampaignSettings(campaignId, { require_human_approval: next })
      setCampaign((c) => (c ? { ...c, require_human_approval: next } : c))
    } finally {
      setBusyApprovalToggle(false)
    }
  }

  const status = campaign?.status ?? 'running'
  const isRunning = status === 'running'

  return (
    <div className="relative min-h-screen bg-neutral-950 text-neutral-100">
      <div className="absolute inset-x-0 top-0 h-72 bg-spotlight pointer-events-none" />

      <div className="relative max-w-[110rem] mx-auto px-6 py-8 flex flex-col gap-4 min-h-screen">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <Link
              href="/"
              className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 hover:text-neutral-300 inline-block mb-3 font-mono transition-colors"
            >
              ← All sessions
            </Link>
            <div className="flex items-center gap-2 mb-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  isRunning
                    ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.6)]'
                    : status === 'meeting_booked'
                      ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]'
                      : 'bg-neutral-500'
                }`}
              />
              <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 font-mono">
                {isRunning
                  ? 'Agent running'
                  : status === 'meeting_booked'
                    ? 'Meeting booked'
                    : 'Paused'}
              </span>
              {campaign?.language && (
                <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-600 font-mono">
                  · outreach in {campaign.language}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-medium tracking-tight text-neutral-100">
              {campaign?.country ?? 'Mission Control'}
            </h1>
            {campaign?.goal && (
              <p className="text-sm text-neutral-400 mt-2 max-w-2xl leading-relaxed">
                {campaign.goal}
              </p>
            )}
            {campaign?.company_url && (
              <a
                href={campaign.company_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block mt-2 text-[11px] text-neutral-500 hover:text-neutral-300 font-mono transition-colors"
              >
                ↗ {campaign.company_url}
              </a>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            {/* Human validation toggle */}
            <button
              onClick={handleToggleApproval}
              disabled={busyApprovalToggle || !campaign}
              title={
                campaign?.require_human_approval
                  ? 'Human validation ON — click to run automatically'
                  : 'Human validation OFF — click to require approval before each action'
              }
              className={`flex items-center gap-2 text-xs border rounded-lg px-3 py-1.5 transition-colors backdrop-blur-sm disabled:opacity-40 disabled:cursor-not-allowed ${
                campaign?.require_human_approval
                  ? 'bg-amber-500/10 border-amber-500/40 text-amber-300 hover:bg-amber-500/20 hover:border-amber-400/60'
                  : 'bg-neutral-900/60 border-neutral-800 text-neutral-500 hover:bg-neutral-800 hover:border-neutral-700 hover:text-neutral-300'
              }`}
            >
              {busyApprovalToggle ? (
                <span className="animate-spin inline-block w-3 h-3 border border-current border-t-transparent rounded-full" />
              ) : campaign?.require_human_approval ? (
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-neutral-600" />
              )}
              <span className="font-mono uppercase tracking-[0.12em] text-[10px]">
                {campaign?.require_human_approval
                  ? 'Human validation ON'
                  : 'Auto-run everything'}
              </span>
            </button>

            {/* Pause button */}
            <button
              onClick={handlePause}
              disabled={!isRunning || busyPause}
              className="text-sm text-neutral-300 border border-neutral-800 bg-neutral-900/60 rounded-lg px-4 py-2 hover:bg-neutral-800 hover:border-neutral-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors backdrop-blur-sm"
            >
              {isRunning ? (busyPause ? 'Pausing…' : 'Pause agent') : 'Paused'}
            </button>
          </div>
        </div>

        {/* Stat cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            {[
              { slug: 'people', label: 'People found', value: stats.total_leads },
              { slug: 'contacted', label: 'People contacted', value: stats.contacted },
              { slug: 'replied', label: 'Replied', value: stats.replied },
              { slug: 'opportunities', label: 'Opportunities', value: stats.total_opportunities },
              { slug: 'pitches', label: 'Pitches sent', value: stats.opportunities_contacted },
              { slug: 'meetings', label: 'Meetings', value: stats.meetings },
            ].map((card) => (
              <StatCardLink
                key={card.slug}
                href={`/dashboard/${campaignId}/${card.slug}`}
                label={card.label}
                value={card.value}
              />
            ))}
          </div>
        )}

        {/* Two-stream main panel */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:h-[34rem]">
          <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-5 backdrop-blur-sm flex flex-col h-[32rem] lg:h-full overflow-hidden">
            <PeopleStream campaignId={campaignId} />
          </div>
          <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-5 backdrop-blur-sm flex flex-col h-[32rem] lg:h-full overflow-hidden">
            <OpportunitiesStream campaignId={campaignId} />
          </div>
        </div>

        {/* Live browser viewers — one per stream */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <BrowserScreen campaignId={campaignId} stream="people" compact />
          <BrowserScreen campaignId={campaignId} stream="opportunities" compact />
        </div>
      </div>
    </div>
  )
}
