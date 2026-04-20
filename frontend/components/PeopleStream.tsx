'use client'

import { useEffect, useState } from 'react'
import { getLeads } from '@/lib/api'
import { useAgentStream } from '@/lib/useAgentStream'
import type { Lead } from '@/lib/types'
import PanelActivityFeed from './PanelActivityFeed'

const faviconUrl = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

const PLATFORM_META: Record<string, { domain: string; badge: string; label: string }> = {
  linkedin:    { domain: 'linkedin.com',    badge: 'bg-sky-500/10 text-sky-300 border-sky-500/30',           label: 'LinkedIn' },
  reddit:      { domain: 'reddit.com',      badge: 'bg-orange-500/10 text-orange-300 border-orange-500/30',  label: 'Reddit' },
  youtube:     { domain: 'youtube.com',     badge: 'bg-red-600/10 text-red-400 border-red-600/30',           label: 'YouTube' },
  instagram:   { domain: 'instagram.com',   badge: 'bg-pink-500/10 text-pink-300 border-pink-500/30',        label: 'Instagram' },
  tiktok:      { domain: 'tiktok.com',      badge: 'bg-neutral-800 text-neutral-300 border-neutral-700',     label: 'TikTok' },
  gmail:       { domain: 'gmail.com',       badge: 'bg-rose-500/10 text-rose-300 border-rose-500/30',        label: 'Gmail' },
  naver:       { domain: 'naver.com',       badge: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30', label: 'Naver' },
  quora:       { domain: 'quora.com',       badge: 'bg-rose-500/10 text-rose-300 border-rose-500/30',        label: 'Quora' },
  zhihu:       { domain: 'zhihu.com',       badge: 'bg-blue-500/10 text-blue-300 border-blue-500/30',        label: 'Zhihu' },
  weibo:       { domain: 'weibo.com',       badge: 'bg-red-500/10 text-red-300 border-red-500/30',           label: 'Weibo' },
  xiaohongshu: { domain: 'xiaohongshu.com', badge: 'bg-pink-500/10 text-pink-300 border-pink-500/30',        label: 'XHS' },
}

const ORDERED_TABS = ['all', 'linkedin', 'reddit', 'instagram', 'youtube', 'tiktok', 'gmail']

const STATUS_BADGE: Record<string, string> = {
  identified: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  contacted:  'bg-blue-500/10 text-blue-300 border-blue-500/30',
  replied:    'bg-amber-500/10 text-amber-300 border-amber-500/30',
  meeting:    'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
}

function LeadCard({ lead }: { lead: Lead }) {
  const platform = (lead.platform || 'linkedin').toLowerCase()
  const meta = PLATFORM_META[platform] || PLATFORM_META.linkedin
  const statusBadge = STATUS_BADGE[lead.status] || STATUS_BADGE.identified
  const isSent = lead.status === 'contacted' || lead.status === 'replied' || lead.status === 'meeting'

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 hover:border-neutral-700 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded-full border ${meta.badge}`}>
              <img src={faviconUrl(meta.domain)} alt={meta.label} width={12} height={12} className="rounded-sm shrink-0" />
              {meta.label}
            </span>
            <p className="text-sm font-medium text-neutral-200 truncate">{lead.name}</p>
          </div>
          {(lead.title || lead.company) && (
            <p className="text-[11px] text-neutral-500 mt-1 truncate">
              {lead.title}{lead.title && lead.company ? ' · ' : ''}{lead.company}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}>
            {lead.status}
          </span>
        </div>
      </div>

      {/* Channel links */}
      <div className="flex items-center gap-1.5 mb-2">
        {lead.linkedin_url && (
          <a href={lead.linkedin_url} target="_blank" rel="noreferrer" title="LinkedIn profile">
            <img src={faviconUrl('linkedin.com')} alt="LinkedIn" width={14} height={14} className="rounded-sm opacity-60 hover:opacity-100 transition-opacity" />
          </a>
        )}
        {lead.source_post_url && (
          <a href={lead.source_post_url} target="_blank" rel="noreferrer" title={`View ${meta.label} post`}>
            <img src={faviconUrl(meta.domain)} alt={meta.label} width={14} height={14} className="rounded-sm opacity-60 hover:opacity-100 transition-opacity" />
          </a>
        )}
        {lead.email && (
          <span title={`Gmail: ${lead.email}`}>
            <img src={faviconUrl('gmail.com')} alt="Gmail" width={14} height={14} className="rounded-sm opacity-60" />
          </span>
        )}
      </div>

      {/* What they said */}
      {lead.source_comment_text && (
        <div className="mt-1 rounded-md bg-neutral-900/60 border border-neutral-800 px-2.5 py-1.5">
          <p className="text-[10px] font-mono uppercase text-neutral-600 mb-1">they said</p>
          <p className="text-[12px] text-neutral-300 leading-snug line-clamp-3">{lead.source_comment_text}</p>
          {lead.source_post_url && (
            <a href={lead.source_post_url} target="_blank" rel="noreferrer"
              className="text-[10px] font-mono text-neutral-500 hover:text-neutral-300 mt-1 inline-block truncate max-w-full">
              ↗ {lead.source_post_url}
            </a>
          )}
        </div>
      )}

      {/* Draft / sent message */}
      {lead.reply_text && (
        <div className={`mt-2 rounded-md px-2.5 py-1.5 border ${isSent ? 'bg-emerald-950/30 border-emerald-900/40' : 'bg-amber-950/20 border-amber-900/30'}`}>
          <div className="flex items-center gap-1.5 mb-1">
            {isSent
              ? <img src={faviconUrl(meta.domain)} alt={meta.label} width={12} height={12} className="rounded-sm" />
              : <span className="text-[9px] font-mono uppercase text-amber-400/70 bg-amber-900/30 px-1.5 py-0.5 rounded">draft</span>
            }
            <p className={`text-[10px] font-mono uppercase ${isSent ? 'text-emerald-400/80' : 'text-amber-400/70'}`}>
              {isSent
                ? `sent via ${meta.label}${lead.reply_language ? ` · ${lead.reply_language}` : ''}`
                : `sample ${meta.label} message${lead.reply_language ? ` · ${lead.reply_language}` : ''}`
              }
            </p>
            {lead.email && isSent && (
              <img src={faviconUrl('gmail.com')} alt="Gmail" width={12} height={12} className="rounded-sm ml-0.5" title="Also sent via Gmail" />
            )}
          </div>
          <p className={`text-[12px] leading-snug whitespace-pre-wrap ${isSent ? 'text-emerald-100/90' : 'text-amber-100/80'}`}>
            {lead.reply_text}
          </p>
        </div>
      )}
    </div>
  )
}

export default function PeopleStream({ campaignId }: { campaignId: string }) {
  const [leads, setLeads] = useState<Lead[]>([])
  const [activeTab, setActiveTab] = useState('all')
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
    return () => { cancelled = true; clearInterval(interval) }
  }, [campaignId])

  const isGmailLead = (l: Lead) =>
    (l.platform || '').toLowerCase() === 'gmail' || !!l.email

  // Build the visible tab list from platforms that actually have leads
  const visibleTabs = ORDERED_TABS.filter(tab => {
    if (tab === 'all') return true
    if (tab === 'gmail') return leads.some(isGmailLead)
    return leads.some(l => (l.platform || 'linkedin').toLowerCase() === tab)
  })

  // Count per tab
  const tabCount = (tab: string) => {
    if (tab === 'all') return leads.length
    if (tab === 'gmail') return leads.filter(isGmailLead).length
    return leads.filter(l => (l.platform || 'linkedin').toLowerCase() === tab).length
  }

  // Filter leads for the active tab
  const filtered =
    activeTab === 'all'   ? leads :
    activeTab === 'gmail' ? leads.filter(isGmailLead) :
    leads.filter(l => (l.platform || 'linkedin').toLowerCase() === activeTab)

  // Reset to 'all' if the active tab disappears (e.g. leads cleared)
  useEffect(() => {
    if (!visibleTabs.includes(activeTab)) setActiveTab('all')
  }, [visibleTabs, activeTab])

  const platformMeta = (tab: string) => PLATFORM_META[tab] || null

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-2 gap-3 px-4 pt-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-medium text-neutral-100">People</h2>
          <p className="text-xs text-neutral-500 mt-0.5">Buyers venting about this pain on social</p>
        </div>
        <span className={`inline-flex items-center gap-1.5 text-[11px] border rounded-full px-2 py-0.5 shrink-0 transition-colors duration-500 ${
          !loaded ? 'text-amber-300/80 border-amber-900/50 bg-amber-950/20' : 'text-neutral-300 border-neutral-800 bg-neutral-900/60'
        }`}>
          <span className={`h-1.5 w-1.5 rounded-full ${!loaded ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400 animate-pulse'}`} />
          {!loaded ? 'scanning…' : 'live'}
        </span>
      </div>

      {/* ── Platform tab bar ─────────────────────────────────── */}
      {leads.length > 0 && (
        <div className="flex items-center gap-1 px-4 pb-2 overflow-x-auto scrollbar-none">
          {visibleTabs.map(tab => {
            const meta = platformMeta(tab)
            const count = tabCount(tab)
            const isActive = activeTab === tab
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`inline-flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded-lg border shrink-0 transition-colors ${
                  isActive
                    ? 'bg-neutral-800 border-neutral-600 text-neutral-100'
                    : 'bg-transparent border-neutral-800 text-neutral-500 hover:text-neutral-300 hover:border-neutral-700'
                }`}
              >
                {meta ? (
                  <img src={faviconUrl(meta.domain)} alt={meta.label} width={12} height={12} className="rounded-sm shrink-0" />
                ) : null}
                <span className="capitalize">{tab === 'all' ? 'All' : meta?.label ?? tab}</span>
                <span className={`text-[10px] tabular-nums ${isActive ? 'text-neutral-400' : 'text-neutral-600'}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
      )}

      {/* ── Scrollable content ───────────────────────────────── */}
      <div className="flex flex-col gap-3 overflow-y-auto px-4 pb-4 flex-1 min-h-0">
        <PanelActivityFeed
          campaignId={campaignId}
          events={events}
          streams={['people', 'system']}
          loaded={loaded}
          emptyLabel="› scanning LinkedIn, Reddit, Instagram, YouTube…"
          cap={leads.length > 0 ? 3 : 60}
        />

        {filtered.length > 0 && (
          <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
            {activeTab === 'all' ? `${leads.length} people found` : `${filtered.length} on ${PLATFORM_META[activeTab]?.label ?? activeTab}`}
          </p>
        )}

        {filtered.map((lead, i) => (
          <LeadCard key={`${lead.source_post_url || lead.name}-${i}`} lead={lead} />
        ))}
      </div>
    </div>
  )
}
