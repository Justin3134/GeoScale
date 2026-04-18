'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentStream } from '@/lib/useAgentStream'
import type { AgentEvent, StreamId } from '@/lib/types'

const STALE_MS = 3 * 60 * 1000

function isLive(ev: AgentEvent): boolean {
  if (!ev.time) return false
  const t = new Date(ev.time).getTime()
  if (isNaN(t)) return false
  return Date.now() - t < STALE_MS
}

interface BrowserSession {
  liveUrl: string
  caption: string
  sessionEnded: boolean
  live: boolean
  idx: number
}

interface ScreenProps {
  liveUrl: string
  caption: string
  fullscreen?: boolean
}

function BrowserFrame({ liveUrl, caption, fullscreen }: ScreenProps) {
  return (
    <div
      className={`relative w-full ${
        fullscreen ? 'h-full' : 'aspect-video'
      } rounded-lg overflow-hidden border border-neutral-800 bg-black`}
    >
      <iframe
        src={liveUrl}
        title={caption}
        className="absolute inset-0 w-full h-full"
        sandbox="allow-scripts allow-same-origin allow-forms"
        allow="clipboard-read; clipboard-write"
      />
    </div>
  )
}

const STREAM_LABELS: Record<StreamId, string> = {
  people: 'People',
  signals: 'Radar',
  opportunities: 'Opportunities',
  system: 'System',
}

export default function BrowserScreen({
  campaignId,
  stream,
  compact = false,
}: {
  campaignId: string
  stream?: StreamId
  compact?: boolean
}) {
  const { events } = useAgentStream(campaignId)
  const [expanded, setExpanded] = useState(false)
  const [activeUrl, setActiveUrl] = useState<string | null>(null)

  // Collect all unique sessions for this stream, in order of first appearance
  const sessions = useMemo<BrowserSession[]>(() => {
    const map = new Map<string, { firstEv: AgentEvent; lastEv: AgentEvent }>()

    for (const ev of events) {
      if (!ev.live_url) continue
      if (stream && ev.stream !== stream) continue
      const url = ev.live_url
      const existing = map.get(url)
      if (!existing) {
        map.set(url, { firstEv: ev, lastEv: ev })
      } else {
        existing.lastEv = ev
      }
    }

    let idx = 1
    const result: BrowserSession[] = []
    for (const [url, { firstEv, lastEv }] of map.entries()) {
      const sessionEnded = !!lastEv.session_ended
      const live = !sessionEnded && isLive(lastEv)
      result.push({
        liveUrl: url,
        caption: firstEv.action ?? 'browser-use',
        sessionEnded,
        live,
        idx: idx++,
      })
    }
    return result
  }, [events, stream])

  // Auto-select the most recently started live session, or the last session
  const preferredUrl = useMemo(() => {
    // Prefer the last live session
    for (let i = sessions.length - 1; i >= 0; i--) {
      if (sessions[i].live) return sessions[i].liveUrl
    }
    // Fall back to last session overall
    return sessions.length > 0 ? sessions[sessions.length - 1].liveUrl : null
  }, [sessions])

  // Keep activeUrl in sync: switch to newest live session automatically,
  // but only if the current selection is gone or ended
  useEffect(() => {
    if (!preferredUrl) return
    setActiveUrl((prev) => {
      // If no selection yet, pick preferred
      if (!prev) return preferredUrl
      // If current selection is still in the sessions list and is live, keep it
      const current = sessions.find((s) => s.liveUrl === prev)
      if (current && current.live) return prev
      // Otherwise jump to preferred
      return preferredUrl
    })
  }, [preferredUrl, sessions])

  useEffect(() => {
    if (!expanded) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  const activeSession = sessions.find((s) => s.liveUrl === activeUrl) ?? null
  const liveCount = sessions.filter((s) => s.live).length
  const hasMultiple = sessions.length > 1

  const streamLabel = stream ? STREAM_LABELS[stream] : null

  const { live, sessionEnded, liveUrl, caption } = activeSession
    ? {
        live: activeSession.live,
        // Treat stale sessions (live_url present, no session_ended event, but
        // last event older than STALE_MS) as ended — they're zombie entries
        // where the backend didn't fire the session_ended event. Without this,
        // the iframe would show Browser Use Cloud's own "Session Ended" screen
        // while our badge still says "live".
        sessionEnded: activeSession.sessionEnded || (!activeSession.live && !!activeSession.liveUrl),
        liveUrl: activeSession.liveUrl,
        caption: activeSession.caption,
      }
    : { live: false, sessionEnded: false, liveUrl: null as string | null, caption: 'browser-use' }

  const titleBase = live
    ? 'Live browser'
    : sessionEnded
      ? 'Session complete'
      : liveUrl
        ? 'Last session'
        : 'Browser'
  const title = streamLabel ? `${streamLabel} · ${titleBase}` : titleBase

  return (
    <>
      <div
        className={`bg-neutral-900/60 border border-neutral-800 rounded-xl backdrop-blur-sm ${
          compact ? 'p-3' : 'p-5'
        }`}
      >
        {/* Header */}
        <div className={`flex items-start justify-between gap-3 ${compact ? 'mb-2' : 'mb-3'}`}>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${
                  live
                    ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.6)]'
                    : sessionEnded
                      ? 'bg-sky-500'
                      : liveUrl
                        ? 'bg-neutral-500'
                        : 'bg-neutral-700'
                }`}
              />
              <h2
                className={`font-medium text-neutral-100 ${
                  compact ? 'text-[13px]' : 'text-[15px]'
                }`}
              >
                {title}
              </h2>
              <span className="inline-flex items-center gap-1.5 text-[10px] text-neutral-300 border border-neutral-800 bg-neutral-900/60 rounded-full px-2 py-0.5">
                browser-use
              </span>
              {liveCount > 1 && (
                <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 border border-emerald-900/60 bg-emerald-950/30 rounded-full px-2 py-0.5 font-mono">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  {liveCount} live
                </span>
              )}
            </div>
            <p
              className={`text-neutral-500 mt-1 truncate ${compact ? 'text-[11px]' : 'text-xs'}`}
            >
              {liveUrl
                ? caption
                : 'Watch the agent comment, DM, and submit forms in real time'}
            </p>
          </div>
          {liveUrl && !sessionEnded && (
            <button
              onClick={() => setExpanded(true)}
              className="text-[11px] text-neutral-300 border border-neutral-800 bg-neutral-900/60 rounded-md px-2.5 py-1 hover:bg-neutral-800 hover:border-neutral-700 transition-colors shrink-0 inline-flex items-center gap-1.5"
              aria-label="Expand browser view"
            >
              <span aria-hidden>⤢</span>
              Expand
            </button>
          )}
        </div>

        {/* Session tabs — only rendered when 2+ sessions exist */}
        {hasMultiple && (
          <div className={`flex items-center gap-1.5 flex-wrap ${compact ? 'mb-2' : 'mb-3'}`}>
            {sessions.map((s) => {
              const isActive = s.liveUrl === activeUrl
              return (
                <button
                  key={s.liveUrl}
                  onClick={() => setActiveUrl(s.liveUrl)}
                  title={s.caption}
                  className={`inline-flex items-center gap-1.5 text-[11px] rounded-md px-2.5 py-1 border transition-colors font-mono ${
                    isActive
                      ? 'border-neutral-600 bg-neutral-800 text-neutral-100'
                      : 'border-neutral-800 bg-neutral-900/40 text-neutral-400 hover:bg-neutral-800/60 hover:text-neutral-200 hover:border-neutral-700'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                      s.live
                        ? 'bg-emerald-400 animate-pulse'
                        : s.sessionEnded
                          ? 'bg-sky-500'
                          : 'bg-neutral-500'
                    }`}
                  />
                  Session {s.idx}
                </button>
              )
            })}
          </div>
        )}

        {/* Browser view */}
        {liveUrl && !sessionEnded ? (
          <div
            className="cursor-zoom-in"
            onClick={() => setExpanded(true)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') setExpanded(true)
            }}
            aria-label="Expand browser view"
          >
            <BrowserFrame liveUrl={liveUrl} caption={caption} />
          </div>
        ) : liveUrl && sessionEnded ? (
          <CompletedState caption={caption} compact={compact} />
        ) : (
          <EmptyState streamLabel={streamLabel} compact={compact} />
        )}
      </div>

      {expanded && liveUrl && !sessionEnded && (
        <FullscreenModal
          liveUrl={liveUrl}
          caption={caption}
          live={!!live}
          onClose={() => setExpanded(false)}
        />
      )}
    </>
  )
}

function EmptyState({
  streamLabel,
  compact,
}: {
  streamLabel?: string | null
  compact?: boolean
}) {
  return (
    <div className="relative w-full aspect-video rounded-lg border border-dashed border-neutral-800 bg-neutral-950/40 overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
      <div
        className={`absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-center ${
          compact ? 'px-3' : 'px-6'
        }`}
      >
        <div className="h-2 w-2 rounded-full bg-neutral-700" />
        <p
          className={`text-neutral-400 ${compact ? 'text-xs' : 'text-sm'}`}
        >
          {streamLabel
            ? `Waiting for ${streamLabel.toLowerCase()} action…`
            : 'Waiting for the agent to take a real-world action…'}
        </p>
        {!compact && (
          <p className="text-xs text-neutral-600 max-w-md">
            When the agent posts a comment, sends a DM, or fills a contact form,
            a live browser view will appear here.
          </p>
        )}
      </div>
    </div>
  )
}

function CompletedState({
  caption,
  compact,
}: {
  caption: string
  compact?: boolean
}) {
  return (
    <div className="relative w-full aspect-video rounded-lg border border-neutral-800 bg-neutral-950/40 overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-20 pointer-events-none" />
      <div
        className={`absolute inset-0 flex flex-col items-center justify-center gap-2 text-center ${
          compact ? 'px-3' : 'px-6'
        }`}
      >
        <div className="h-2 w-2 rounded-full bg-sky-500" />
        <p className={`text-neutral-300 font-medium ${compact ? 'text-xs' : 'text-sm'}`}>
          Session complete
        </p>
        {!compact && (
          <p className="text-xs text-neutral-500 max-w-xs leading-relaxed">{caption}</p>
        )}
      </div>
    </div>
  )
}

function FullscreenModal({
  liveUrl,
  caption,
  live,
  onClose,
}: {
  liveUrl: string
  caption: string
  live: boolean
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Live browser view"
    >
      <div
        className="relative w-full max-w-[90vw] max-h-[90vh] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className={`h-2 w-2 rounded-full ${
                live
                  ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.6)]'
                  : 'bg-neutral-500'
              }`}
            />
            <span className="text-sm text-neutral-200 truncate">{caption}</span>
            <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-neutral-500">
              browser-use
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-sm text-neutral-300 border border-neutral-800 bg-neutral-900/80 rounded-md px-3 py-1.5 hover:bg-neutral-800 hover:border-neutral-700 transition-colors"
            aria-label="Close"
          >
            Close ✕
          </button>
        </div>
        <div className="flex-1 min-h-0 aspect-video max-h-[80vh] mx-auto w-full">
          <BrowserFrame liveUrl={liveUrl} caption={caption} fullscreen />
        </div>
      </div>
    </div>
  )
}
