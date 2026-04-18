'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { deleteCampaign, getCampaigns } from '@/lib/api'
import type { Campaign, CampaignStatus } from '@/lib/types'

const STATUS_DOT: Record<CampaignStatus, string> = {
  running: 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.6)]',
  paused: 'bg-neutral-500',
  meeting_booked: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]',
}

const STATUS_LABEL: Record<CampaignStatus, string> = {
  running: 'Running',
  paused: 'Paused',
  meeting_booked: 'Meeting booked',
}

function formatAge(iso?: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (isNaN(t)) return ''
  const diffMs = Date.now() - t
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ${mins % 60}m`
  const days = Math.floor(hrs / 24)
  return `${days}d ${hrs % 24}h`
}

export default function CampaignsList() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await getCampaigns()
        if (cancelled) return
        setCampaigns(data)
        setError(null)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Failed to load sessions')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const interval = setInterval(load, 10_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const handleDelete = async (
    e: React.MouseEvent,
    campaign: Campaign,
  ) => {
    e.preventDefault()
    e.stopPropagation()
    const ok = window.confirm(
      `Delete this session for ${campaign.country}? This removes all leads, opportunities, signals, and actions. This cannot be undone.`,
    )
    if (!ok) return
    setDeletingId(campaign.id)
    try {
      await deleteCampaign(campaign.id)
      setCampaigns((prev) => prev.filter((c) => c.id !== campaign.id))
    } catch (err) {
      alert(
        err instanceof Error ? err.message : 'Failed to delete session',
      )
    } finally {
      setDeletingId(null)
    }
  }

  if (loading && campaigns.length === 0) {
    return (
      <div className="rounded-2xl bg-neutral-900/60 border border-neutral-800 p-6 max-w-xl mx-auto mt-6">
        <p className="text-sm text-neutral-500">Loading sessions…</p>
      </div>
    )
  }

  if (error && campaigns.length === 0) {
    return (
      <div className="rounded-2xl bg-neutral-900/60 border border-neutral-800 p-6 max-w-xl mx-auto mt-6">
        <p className="text-sm text-rose-400">Couldn’t load sessions.</p>
        <p className="text-xs text-neutral-500 mt-1 font-mono break-all">
          {error}
        </p>
      </div>
    )
  }

  if (campaigns.length === 0) {
    return (
      <div className="rounded-2xl bg-neutral-900/60 border border-neutral-800 p-6 max-w-xl mx-auto mt-6">
        <p className="text-sm text-neutral-500">No sessions yet — deploy your first agent above.</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl bg-neutral-900/60 border border-neutral-800 p-6 max-w-xl mx-auto mt-6 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 font-mono">
            Active sessions
          </span>
        </div>
        <span className="text-[11px] text-neutral-600 font-mono">
          {campaigns.length} total
        </span>
      </div>
      <div className="flex flex-col divide-y divide-neutral-800/60">
        {campaigns.map((c) => {
          const status = (c.status ?? 'running') as CampaignStatus
          const isDeleting = deletingId === c.id
          return (
            <div
              key={c.id}
              className="group relative flex items-center justify-between py-3 -mx-2 px-2 rounded-lg hover:bg-neutral-800/40 transition-colors"
            >
              <Link
                href={`/dashboard/${c.id}`}
                className="flex items-center justify-between flex-1 min-w-0 gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${STATUS_DOT[status] ?? 'bg-neutral-500'}`}
                    />
                    <p className="text-sm font-medium text-neutral-100 truncate">
                      {c.country}
                    </p>
                    <span className="text-[11px] text-neutral-500 font-mono">
                      {STATUS_LABEL[status] ?? status}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-500 mt-1 truncate">
                    {c.goal || c.company_url || '—'}
                  </p>
                </div>
                <div className="flex flex-col items-end shrink-0">
                  <span className="text-[11px] text-neutral-500 font-mono">
                    {formatAge(c.created_at)}
                  </span>
                  <span className="text-[11px] text-neutral-600 mt-0.5 font-mono">
                    {(c.total_leads ?? 0)} ppl · {(c.total_opportunities ?? 0)} opps · {(c.total_actions ?? 0)} acts
                  </span>
                </div>
              </Link>
              <button
                type="button"
                onClick={(e) => handleDelete(e, c)}
                disabled={isDeleting}
                aria-label={`Delete session for ${c.country}`}
                title="Delete session"
                className="ml-2 shrink-0 p-1.5 rounded-md text-neutral-500 opacity-0 group-hover:opacity-100 hover:text-rose-400 hover:bg-rose-500/10 focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-rose-500/40 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeleting ? (
                  <svg
                    className="w-4 h-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeOpacity="0.25"
                    />
                    <path
                      d="M22 12a10 10 0 0 1-10 10"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                  </svg>
                ) : (
                  <svg
                    className="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M3 6h18" />
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6" />
                    <path d="M14 11v6" />
                  </svg>
                )}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
