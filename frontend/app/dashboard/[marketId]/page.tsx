'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import BrowserScreen from '@/components/BrowserScreen'
import OutreachPanel from '@/components/OutreachPanel'
import PanelActivityFeed from '@/components/PanelActivityFeed'
import { getCampaign, getLeads, pauseCampaign, updateCampaignSettings } from '@/lib/api'
import { useAgentStream } from '@/lib/useAgentStream'
import type { Campaign, Lead } from '@/lib/types'

const faviconUrl = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

const PLATFORM_TABS = [
  { id: 'all',       label: 'All',       domain: null },
  { id: 'linkedin',  label: 'LinkedIn',  domain: 'linkedin.com' },
  { id: 'reddit',    label: 'Reddit',    domain: 'reddit.com' },
  { id: 'instagram', label: 'Instagram', domain: 'instagram.com' },
  { id: 'youtube',   label: 'YouTube',   domain: 'youtube.com' },
  { id: 'gmail',     label: 'Gmail',     domain: 'gmail.com' },
] as const

type PlatformId = (typeof PLATFORM_TABS)[number]['id']

export default function DashboardPage() {
  const params = useParams<{ marketId: string }>()
  const campaignId = params?.marketId as string

  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [activePlatform, setActivePlatform] = useState<PlatformId>('all')
  const [busyPause, setBusyPause] = useState(false)
  const [busyApprovalToggle, setBusyApprovalToggle] = useState(false)
  const [approvalError, setApprovalError] = useState<string | null>(null)
  const { events, loaded } = useAgentStream(campaignId)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false

    const load = async () => {
      try {
        const [c, l] = await Promise.all([
          getCampaign(campaignId),
          getLeads(campaignId),
        ])
        if (cancelled) return
        setCampaign(c)
        setLeads(l)
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

  // Immediately refresh leads when the backend signals new leads were saved.
  // This fires well before the next 10-second poll so the UI stays in sync.
  useEffect(() => {
    if (!campaignId || events.length === 0) return
    const latest = events[events.length - 1]
    if (latest?.type === 'leads_updated') {
      getLeads(campaignId)
        .then((l) => setLeads(l))
        .catch(() => {/* ignore */})
    }
  }, [campaignId, events])

  const handleToggleApproval = async () => {
    if (!campaign) return
    setBusyApprovalToggle(true)
    setApprovalError(null)
    const next = !campaign.require_human_approval
    try {
      await updateCampaignSettings(campaignId, { require_human_approval: next })
      setCampaign((c) => (c ? { ...c, require_human_approval: next } : c))
    } catch (err) {
      setApprovalError(err instanceof Error ? err.message : 'Failed to update settings')
    } finally {
      setBusyApprovalToggle(false)
    }
  }

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
            {approvalError && (
              <span className="text-[10px] text-red-400 font-mono max-w-[18rem] text-right">
                {approvalError}
              </span>
            )}
            {/* Human verification toggle */}
            <button
              onClick={handleToggleApproval}
              disabled={busyApprovalToggle || !campaign}
              title={
                campaign?.require_human_approval
                  ? 'Human verification ON — click to auto-run everything'
                  : 'Auto-run everything — click to require human verification'
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
                  ? 'Human verification ON'
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


        {/* ── Platform nav ─────────────────────────────────── */}
        <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pb-1">
          {PLATFORM_TABS.map(tab => {
            const count =
              tab.id === 'all'   ? leads.length :
              tab.id === 'gmail' ? leads.filter(l => (l.platform || '').toLowerCase() === 'gmail' || !!l.email).length :
              leads.filter(l => (l.platform || 'linkedin').toLowerCase() === tab.id).length
            const isActive = activePlatform === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActivePlatform(tab.id)}
                className={`inline-flex items-center gap-1.5 text-[12px] font-mono px-3 py-1.5 rounded-lg border shrink-0 transition-colors ${
                  isActive
                    ? 'bg-neutral-800 border-neutral-600 text-neutral-100'
                    : 'bg-neutral-900/50 border-neutral-800 text-neutral-500 hover:text-neutral-300 hover:border-neutral-700'
                }`}
              >
                {tab.domain ? (
                  <img
                    src={faviconUrl(tab.domain)}
                    alt={tab.label}
                    width={14}
                    height={14}
                    className="rounded-sm shrink-0"
                  />
                ) : (
                  <span className="w-3.5 h-3.5 flex items-center justify-center text-[10px]">⊞</span>
                )}
                {tab.label}
                <span className={`text-[11px] tabular-nums ml-0.5 ${isActive ? 'text-neutral-400' : 'text-neutral-700'}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {/* ── Main panel — agent log left, outreach right ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 lg:h-[36rem]">
          {/* Left: agent activity log */}
          <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-5 backdrop-blur-sm flex flex-col h-[32rem] lg:h-full overflow-hidden">
            <div className="flex items-start justify-between mb-3 gap-3">
              <div className="min-w-0">
                <h2 className="text-[15px] font-medium text-neutral-100">Agent log</h2>
                <p className="text-xs text-neutral-500 mt-0.5">
                  {activePlatform === 'all'
                    ? 'All streams — scans, scoring & outreach'
                    : `${PLATFORM_TABS.find(t => t.id === activePlatform)?.label ?? activePlatform} — scraping, scoring & outreach`}
                </p>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 text-[11px] border rounded-full px-2 py-0.5 shrink-0 transition-colors duration-500 ${
                  !loaded
                    ? 'text-amber-300/80 border-amber-900/50 bg-amber-950/20'
                    : 'text-neutral-300 border-neutral-800 bg-neutral-900/60'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    !loaded ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400 animate-pulse'
                  }`}
                />
                {!loaded ? 'loading…' : 'live'}
              </span>
            </div>
            <PanelActivityFeed
              campaignId={campaignId}
              events={events}
              streams={['people', 'signals', 'system']}
              loaded={loaded}
              emptyLabel="› agent is warming up…"
              cap={120}
              platform={activePlatform}
            />
          </div>

          {/* Right: outreach channels */}
          <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-5 backdrop-blur-sm flex flex-col h-[32rem] lg:h-full overflow-hidden">
            <OutreachPanel
              campaignId={campaignId}
              leads={leads}
              activePlatform={activePlatform}
              events={events}
              loaded={loaded}
            />
          </div>
        </div>

        {/* Live browser viewer */}
        <div className="grid grid-cols-1 gap-3">
          <BrowserScreen campaignId={campaignId} stream="people" compact />
        </div>
      </div>
    </div>
  )
}
