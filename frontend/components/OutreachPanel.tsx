'use client'

import { useCallback, useMemo, useState } from 'react'
import { approveAction, rejectAction, sendGmailLead } from '@/lib/api'
import type { AgentEvent, Lead } from '@/lib/types'

const faviconUrl = (domain: string) =>
  `https://www.google.com/s2/favicons?domain=${domain}&sz=32`

const PLATFORM_META: Record<string, {
  domain: string
  badge: string
  label: string
  color: string
  hint: string
}> = {
  linkedin:    { domain: 'linkedin.com',    badge: 'bg-sky-500/10 text-sky-300 border-sky-500/30',             label: 'LinkedIn',  color: 'text-sky-400',     hint: 'Connect & reply to their posts' },
  reddit:      { domain: 'reddit.com',      badge: 'bg-orange-500/10 text-orange-300 border-orange-500/30',    label: 'Reddit',    color: 'text-orange-400',  hint: 'Reply to posts in relevant threads' },
  youtube:     { domain: 'youtube.com',     badge: 'bg-red-600/10 text-red-400 border-red-600/30',             label: 'YouTube',   color: 'text-red-400',     hint: 'Comment on relevant videos' },
  instagram:   { domain: 'instagram.com',   badge: 'bg-pink-500/10 text-pink-300 border-pink-500/30',          label: 'Instagram', color: 'text-pink-400',    hint: 'Comment on relevant posts' },
  tiktok:      { domain: 'tiktok.com',      badge: 'bg-neutral-800 text-neutral-300 border-neutral-700',       label: 'TikTok',    color: 'text-neutral-300', hint: 'Comment on relevant videos' },
  gmail:       { domain: 'gmail.com',       badge: 'bg-rose-500/10 text-rose-300 border-rose-500/30',          label: 'Gmail',     color: 'text-rose-400',    hint: 'Cold outreach to enriched contacts' },
  naver:       { domain: 'naver.com',       badge: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30', label: 'Naver',     color: 'text-emerald-400', hint: 'Reply to posts' },
  quora:       { domain: 'quora.com',       badge: 'bg-rose-500/10 text-rose-300 border-rose-500/30',          label: 'Quora',     color: 'text-rose-400',    hint: 'Answer relevant questions' },
  zhihu:       { domain: 'zhihu.com',       badge: 'bg-blue-500/10 text-blue-300 border-blue-500/30',          label: 'Zhihu',     color: 'text-blue-400',    hint: 'Answer relevant questions' },
  weibo:       { domain: 'weibo.com',       badge: 'bg-red-500/10 text-red-300 border-red-500/30',             label: 'Weibo',     color: 'text-red-300',     hint: 'Comment on relevant posts' },
  xiaohongshu: { domain: 'xiaohongshu.com', badge: 'bg-pink-500/10 text-pink-300 border-pink-500/30',          label: 'XHS',       color: 'text-pink-300',    hint: 'Comment on relevant posts' },
}

const STATUS_BADGE: Record<string, string> = {
  identified: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  contacted:  'bg-blue-500/10 text-blue-300 border-blue-500/30',
  replied:    'bg-amber-500/10 text-amber-300 border-amber-500/30',
  meeting:    'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
}

interface Props {
  campaignId: string
  leads: Lead[]
  activePlatform: string
  events: AgentEvent[]
  loaded: boolean
}

export default function OutreachPanel({ campaignId, leads, activePlatform, events, loaded }: Props) {
  const [resolvedApprovals, setResolvedApprovals] = useState<Record<string, 'approved' | 'rejected'>>({})
  const [busyApproval, setBusyApproval] = useState<Record<string, 'approve' | 'reject'>>({})
  const [gmailSending, setGmailSending] = useState<Record<number, boolean>>({})
  const [gmailSent, setGmailSent] = useState<Record<number, boolean>>({})

  const handleApproval = useCallback(
    async (approvalId: string, action: 'approve' | 'reject') => {
      if (!campaignId || resolvedApprovals[approvalId]) return
      setBusyApproval((prev) => ({ ...prev, [approvalId]: action }))
      try {
        if (action === 'approve') {
          await approveAction(campaignId, approvalId)
        } else {
          await rejectAction(campaignId, approvalId)
        }
        setResolvedApprovals((prev) => ({ ...prev, [approvalId]: action === 'approve' ? 'approved' : 'rejected' }))
      } catch {
        setResolvedApprovals((prev) => ({ ...prev, [approvalId]: action === 'approve' ? 'approved' : 'rejected' }))
      } finally {
        setBusyApproval((prev) => { const n = { ...prev }; delete n[approvalId]; return n })
      }
    },
    [campaignId, resolvedApprovals],
  )

  const handleGmailSend = useCallback(
    async (leadId: number) => {
      if (gmailSending[leadId] || gmailSent[leadId]) return
      setGmailSending((prev) => ({ ...prev, [leadId]: true }))
      try {
        await sendGmailLead(campaignId, leadId)
        setGmailSent((prev) => ({ ...prev, [leadId]: true }))
      } catch {
        // surface nothing — browser-use runs async, status updates via leads poll
        setGmailSent((prev) => ({ ...prev, [leadId]: true }))
      } finally {
        setGmailSending((prev) => { const n = { ...prev }; delete n[leadId]; return n })
      }
    },
    [campaignId, gmailSending, gmailSent],
  )

  // Build map: target_url → approval_id from the most recent pending preview events
  const pendingByUrl = useMemo(() => {
    const map: Record<string, string> = {}
    for (const ev of events) {
      if (ev.type === 'preview' && ev.preview?.approval_id && ev.preview?.target_url) {
        map[ev.preview.target_url] = ev.preview.approval_id
      }
    }
    return map
  }, [events])

  const filtered =
    activePlatform === 'all' ? leads :
    leads.filter(l => (l.platform || 'linkedin').toLowerCase() === activePlatform)

  const activeMeta = activePlatform !== 'all' ? PLATFORM_META[activePlatform] : null

  const sentFiltered  = filtered.filter(l => l.status === 'contacted' || l.status === 'replied' || l.status === 'meeting')
  const draftFiltered = filtered.filter(l => l.status === 'identified' && l.reply_text)
  const foundFiltered = filtered.filter(l => !l.reply_text)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-3 gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-medium text-neutral-100">Outreach</h2>
          <p className="text-xs text-neutral-500 mt-0.5">
            {activeMeta ? activeMeta.hint : 'Messages sent & drafts per channel'}
          </p>
        </div>
        <span className={`inline-flex items-center gap-1.5 text-[11px] border rounded-full px-2 py-0.5 shrink-0 transition-colors duration-500 ${
          !loaded ? 'text-amber-300/80 border-amber-900/50 bg-amber-950/20' : 'text-neutral-300 border-neutral-800 bg-neutral-900/60'
        }`}>
          <span className={`h-1.5 w-1.5 rounded-full ${!loaded ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400 animate-pulse'}`} />
          {!loaded ? 'scanning…' : 'live'}
        </span>
      </div>

      {/* ── Content ────────────────────────────────────────── */}
      <div className="flex flex-col gap-2 overflow-y-auto flex-1 min-h-0">
        {!loaded ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-[11px] font-mono text-neutral-600">
              › scanning LinkedIn, Reddit, Instagram, YouTube…
            </p>
          </div>
        ) : leads.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-[11px] font-mono text-neutral-600">
              › waiting for first leads…
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-[11px] font-mono text-neutral-600">
              › no {activeMeta?.label ?? ''} leads yet
            </p>
          </div>
        ) : (
          <>
            {sentFiltered.length > 0 && (
              <>
                <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
                  Sent · {sentFiltered.length}
                </p>
                {sentFiltered.map((lead, i) => (
                  <LeadCard key={`sent-${lead.source_post_url || lead.name}-${i}`} lead={lead} />
                ))}
              </>
            )}
            {draftFiltered.length > 0 && (
              <>
                <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
                  Drafts · {draftFiltered.length}
                </p>
                {draftFiltered.map((lead, i) => {
                  // Mirror the target_url fallback in _reach_out:
                  // LinkedIn → post_url || profile_url, Reddit → post_url || username
                  const targetKey = lead.source_post_url || lead.linkedin_url || lead.name || ''
                  const approvalId = targetKey ? pendingByUrl[targetKey] : undefined
                  return (
                    <LeadCard
                      key={`draft-${lead.source_post_url || lead.name}-${i}`}
                      lead={lead}
                      approvalId={approvalId}
                      approvalResolution={approvalId ? resolvedApprovals[approvalId] : undefined}
                      approvalBusy={approvalId ? busyApproval[approvalId] : undefined}
                      onApproval={handleApproval}
                      gmailSending={lead.id !== undefined ? gmailSending[lead.id] : false}
                      gmailSent={lead.id !== undefined ? gmailSent[lead.id] : false}
                      onGmailSend={lead.id !== undefined ? () => handleGmailSend(lead.id!) : undefined}
                    />
                  )
                })}
              </>
            )}
            {foundFiltered.length > 0 && (
              <>
                <p className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-600 pt-1 border-t border-neutral-800/60">
                  Found · {foundFiltered.length}
                </p>
                {foundFiltered.map((lead, i) => (
                  <LeadCard key={`found-${lead.source_post_url || lead.name}-${i}`} lead={lead} />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

interface LeadCardProps {
  lead: Lead
  approvalId?: string
  approvalResolution?: 'approved' | 'rejected'
  approvalBusy?: 'approve' | 'reject'
  onApproval?: (approvalId: string, action: 'approve' | 'reject') => void
  gmailSending?: boolean
  gmailSent?: boolean
  onGmailSend?: () => void
}

function LeadCard({ lead, approvalId, approvalResolution, approvalBusy, onApproval, gmailSending, gmailSent, onGmailSend }: LeadCardProps) {
  const platform = (lead.platform || 'linkedin').toLowerCase()
  const meta = PLATFORM_META[platform] || PLATFORM_META.linkedin
  const statusBadge = STATUS_BADGE[lead.status] || STATUS_BADGE.identified
  const isSent = lead.status === 'contacted' || lead.status === 'replied' || lead.status === 'meeting'

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3 hover:border-neutral-700 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded-full border ${meta.badge}`}>
              <img src={faviconUrl(meta.domain)} alt={meta.label} width={12} height={12} className="rounded-sm shrink-0" />
              {meta.label}
            </span>
            {lead.linkedin_url ? (
            <a
              href={lead.linkedin_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-neutral-200 truncate hover:text-neutral-100 hover:underline"
            >
              {lead.name}
            </a>
          ) : (
            <p className="text-sm font-medium text-neutral-200 truncate">{lead.name}</p>
          )}
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

      {/* What they said */}
      {lead.source_comment_text && (
        <div className="mb-2 rounded-md bg-neutral-900/60 border border-neutral-800 px-2.5 py-1.5">
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

      {/* Message draft / sent */}
      {lead.reply_text && (
        <div className={`rounded-md px-2.5 py-1.5 border ${isSent ? 'bg-emerald-950/30 border-emerald-900/40' : 'bg-amber-950/20 border-amber-900/30'}`}>
          <div className="flex items-center gap-1.5 mb-1">
            <img src={faviconUrl(meta.domain)} alt={meta.label} width={12} height={12} className="rounded-sm" />
            {!isSent && (
              <span className="text-[9px] font-mono uppercase text-amber-400/70 bg-amber-900/30 px-1.5 py-0.5 rounded">draft</span>
            )}
            <p className={`text-[10px] font-mono uppercase ${isSent ? 'text-emerald-400/80' : 'text-amber-400/70'}`}>
              {isSent
                ? `sent via ${meta.label}${lead.reply_language ? ` · ${lead.reply_language}` : ''}`
                : `draft for ${meta.label}${lead.reply_language ? ` · ${lead.reply_language}` : ''}`}
            </p>
            {lead.email && isSent && (
              <img src={faviconUrl('gmail.com')} alt="Gmail" width={12} height={12} className="rounded-sm ml-0.5" title="Also sent via Gmail" />
            )}
          </div>
          <p className={`text-[12px] leading-snug whitespace-pre-wrap ${isSent ? 'text-emerald-100/90' : 'text-amber-100/80'}`}>
            {lead.reply_text}
          </p>
          {!isSent && approvalId && onApproval && (
            <div className="mt-2 flex items-center gap-2">
              {approvalResolution ? (
                <span className={`text-[10px] font-mono uppercase tracking-wider ${approvalResolution === 'approved' ? 'text-emerald-400/70' : 'text-neutral-500'}`}>
                  {approvalResolution === 'approved' ? '✓ sent' : '✗ skipped'}
                </span>
              ) : (
                <>
                  <button
                    onClick={() => onApproval(approvalId, 'approve')}
                    disabled={!!approvalBusy}
                    className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {approvalBusy === 'approve' ? (
                      <span className="animate-spin inline-block w-2 h-2 border border-emerald-400 border-t-transparent rounded-full" />
                    ) : (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    )}
                    Run it
                  </button>
                  <button
                    onClick={() => onApproval(approvalId, 'reject')}
                    disabled={!!approvalBusy}
                    className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-neutral-800/60 border border-neutral-700 text-neutral-400 hover:bg-neutral-700/60 hover:text-neutral-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {approvalBusy === 'reject' ? (
                      <span className="animate-spin inline-block w-2 h-2 border border-neutral-500 border-t-transparent rounded-full" />
                    ) : (
                      <span className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
                    )}
                    Skip
                  </button>
                </>
              )}
            </div>
          )}
          {!isSent && platform === 'gmail' && onGmailSend && (
            <div className="mt-2 flex items-center gap-2">
              {gmailSent ? (
                <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400/70">
                  ✓ sending via browser
                </span>
              ) : (
                <button
                  onClick={onGmailSend}
                  disabled={!!gmailSending}
                  className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono bg-rose-500/15 border border-rose-500/40 text-rose-300 hover:bg-rose-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {gmailSending ? (
                    <span className="animate-spin inline-block w-2 h-2 border border-rose-400 border-t-transparent rounded-full" />
                  ) : (
                    <img src={faviconUrl('gmail.com')} alt="Gmail" width={10} height={10} className="rounded-sm" />
                  )}
                  Send via Gmail
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
