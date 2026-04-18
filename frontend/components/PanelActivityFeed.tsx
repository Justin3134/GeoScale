'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { approveAction, rejectAction } from '@/lib/api'
import type { AgentEvent, AgentEventType, StreamId } from '@/lib/types'

const TYPE_DOT: Record<AgentEventType, string> = {
  scan: 'bg-sky-400',
  think: 'bg-violet-400',
  act: 'bg-emerald-400',
  preview: 'bg-fuchsia-400 animate-pulse',
  wait: 'bg-amber-400',
  escalate: 'bg-rose-400',
  error: 'bg-rose-500',
}

const CHANNEL_LABEL: Record<string, string> = {
  apify: 'apify',
  llm: 'do·llama',
  'browser-use': 'browser-use',
  linkedin: 'linkedin',
  reddit: 'reddit',
  youtube: 'youtube',
  tiktok: 'tiktok',
  naver: 'naver',
  quora: 'quora',
  zhihu: 'zhihu',
  weibo: 'weibo',
  blind: 'blind',
}

function formatTime(time?: string): string {
  if (!time) return '--:--:--'
  const d = new Date(time)
  if (isNaN(d.getTime())) return time
  return d.toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

type ApprovalState = 'pending' | 'approved' | 'rejected' | 'expired'

interface ApprovalButtonsProps {
  campaignId: string
  approvalId: string
  onResolved: (approvalId: string, decision: 'approved' | 'rejected') => void
}

function ApprovalButtons({ campaignId, approvalId, onResolved }: ApprovalButtonsProps) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)

  const handle = useCallback(
    async (action: 'approve' | 'reject') => {
      setBusy(action)
      try {
        if (action === 'approve') {
          await approveAction(campaignId, approvalId)
          onResolved(approvalId, 'approved')
        } else {
          await rejectAction(campaignId, approvalId)
          onResolved(approvalId, 'rejected')
        }
      } catch {
        // If 404, the approval expired — still mark locally
        onResolved(approvalId, action === 'approve' ? 'approved' : 'rejected')
      } finally {
        setBusy(null)
      }
    },
    [campaignId, approvalId, onResolved],
  )

  return (
    <div className="flex items-center gap-2 mt-2">
      <button
        onClick={() => handle('approve')}
        disabled={busy !== null}
        className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-mono font-medium bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 hover:border-emerald-400/60 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {busy === 'approve' ? (
          <span className="animate-spin inline-block w-2.5 h-2.5 border border-emerald-400 border-t-transparent rounded-full" />
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        )}
        Run it
      </button>
      <button
        onClick={() => handle('reject')}
        disabled={busy !== null}
        className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-mono font-medium bg-neutral-800/60 border border-neutral-700 text-neutral-400 hover:bg-neutral-700/60 hover:text-neutral-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {busy === 'reject' ? (
          <span className="animate-spin inline-block w-2.5 h-2.5 border border-neutral-500 border-t-transparent rounded-full" />
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
        )}
        Skip
      </button>
    </div>
  )
}

interface Props {
  campaignId?: string
  events: AgentEvent[]
  streams: StreamId[]
  loaded?: boolean
  emptyLabel?: string
  cap?: number
}

export default function PanelActivityFeed({
  campaignId,
  events,
  streams,
  loaded = true,
  emptyLabel = '› awaiting first action…',
  cap = 60,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Track decisions made this session so buttons disappear after clicking
  const [resolved, setResolved] = useState<Record<string, ApprovalState>>({})

  const handleResolved = useCallback(
    (approvalId: string, decision: 'approved' | 'rejected') => {
      setResolved((prev) => ({ ...prev, [approvalId]: decision }))
    },
    [],
  )

  const filtered = useMemo(() => {
    const allow = new Set(streams)
    return events.filter((ev) => allow.has((ev.stream || 'system') as StreamId))
  }, [events, streams])

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [filtered.length])

  const visible = filtered.slice(-cap)

  if (!loaded) {
    return (
      <p className="text-sm text-neutral-500 font-mono px-1">› loading…</p>
    )
  }

  if (visible.length === 0) {
    return (
      <p className="text-sm text-neutral-500 font-mono px-1">{emptyLabel}</p>
    )
  }

  return (
    <div
      ref={containerRef}
      className="flex flex-col gap-1.5 overflow-y-auto pr-1 flex-1 min-h-0"
    >
      {visible.map((ev, i) => {
        const dot = TYPE_DOT[ev.type] || 'bg-neutral-500'
        const channel = ev.channel
          ? CHANNEL_LABEL[ev.channel] || ev.channel
          : ''
        const approvalId = ev.preview?.approval_id ?? null
        const approvalState = approvalId ? (resolved[approvalId] ?? 'pending') : null
        const isAwaitingApproval = approvalState === 'pending' && !!campaignId && !!approvalId

        return (
          <div
            key={`${ev.time || 'evt'}-${i}`}
            className={`rounded-md border px-2.5 py-1.5 ${
              ev.type === 'preview'
                ? 'border-fuchsia-900/50 bg-fuchsia-950/15'
                : 'border-neutral-800 bg-neutral-950/60'
            }`}
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className={`w-1.5 h-1.5 rounded-full ${dot}`} aria-hidden />
              <span className="text-[9px] font-mono uppercase tracking-wider text-neutral-600">
                {formatTime(ev.time)}
              </span>
              {channel && (
                <span className="text-[9px] font-mono uppercase tracking-wider text-neutral-500">
                  {channel}
                </span>
              )}
              <span className="text-[9px] font-mono uppercase tracking-wider text-neutral-600">
                {ev.type}
              </span>
              {ev.type === 'preview' && approvalState && (
                <span
                  className={`ml-auto text-[9px] font-mono uppercase tracking-wider shrink-0 ${
                    approvalState === 'approved'
                      ? 'text-emerald-400'
                      : approvalState === 'rejected'
                        ? 'text-neutral-500'
                        : approvalState === 'expired'
                          ? 'text-amber-500'
                          : 'text-fuchsia-400 animate-pulse'
                  }`}
                >
                  {approvalState === 'approved'
                    ? '✓ approved'
                    : approvalState === 'rejected'
                      ? '✗ skipped'
                      : approvalState === 'expired'
                        ? 'expired'
                        : '⏳ awaiting'}
                </span>
              )}
              {ev.live_url && (
                <a
                  href={ev.live_url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto text-[10px] font-mono text-emerald-400 hover:text-emerald-300 shrink-0"
                >
                  ↗ live
                </a>
              )}
            </div>

            <p className="text-[12px] text-neutral-200 leading-snug">
              {ev.action}
            </p>
            {ev.reasoning && (
              <p className="text-[11px] text-neutral-500 leading-snug mt-0.5 line-clamp-2">
                {ev.reasoning}
              </p>
            )}

            {/* Preview body — show drafted message */}
            {ev.type === 'preview' && ev.preview?.body_local && (
              <div className="mt-2 rounded border border-fuchsia-900/40 bg-fuchsia-950/20 px-2 py-1.5">
                {ev.preview.subject && (
                  <p className="text-[10px] font-mono uppercase tracking-wider text-fuchsia-400 mb-1">
                    subj: {ev.preview.subject}
                  </p>
                )}
                <p className="text-[12px] text-fuchsia-100 leading-snug whitespace-pre-wrap break-words">
                  {ev.preview.body_local}
                </p>
                {ev.preview.english_gloss && (
                  <p className="mt-1 text-[10.5px] text-neutral-500 italic leading-snug">
                    ↳ {ev.preview.english_gloss}
                  </p>
                )}
                {ev.preview.target_url && (
                  <a
                    href={ev.preview.target_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-[10px] font-mono text-fuchsia-400 hover:text-fuchsia-300 truncate max-w-full"
                  >
                    ↗ {ev.preview.target_url}
                  </a>
                )}

                {/* Approval buttons — only when waiting for human decision */}
                {isAwaitingApproval && (
                  <ApprovalButtons
                    campaignId={campaignId!}
                    approvalId={approvalId!}
                    onResolved={handleResolved}
                  />
                )}
                {approvalState === 'approved' && !isAwaitingApproval && (
                  <p className="mt-2 text-[10px] font-mono text-emerald-400">
                    ✓ Approved — browser-use running
                  </p>
                )}
                {approvalState === 'rejected' && !isAwaitingApproval && (
                  <p className="mt-2 text-[10px] font-mono text-neutral-500">
                    ✗ Skipped by you
                  </p>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
