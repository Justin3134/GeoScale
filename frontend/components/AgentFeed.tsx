'use client'

import { useEffect, useRef, useState } from 'react'
import { getActions, streamEvents } from '@/lib/api'
import type { AgentEvent, AgentEventType } from '@/lib/types'

const TYPE_CONFIG: Record<
  AgentEventType,
  { label: string; dot: string; text: string }
> = {
  scan: {
    label: 'scan',
    dot: 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.7)]',
    text: 'text-sky-300',
  },
  think: {
    label: 'think',
    dot: 'bg-violet-400 shadow-[0_0_6px_rgba(167,139,250,0.7)]',
    text: 'text-violet-300',
  },
  act: {
    label: 'act',
    dot: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]',
    text: 'text-emerald-300',
  },
  preview: {
    label: 'about to send',
    dot: 'bg-fuchsia-400 shadow-[0_0_6px_rgba(232,121,249,0.7)] animate-pulse',
    text: 'text-fuchsia-300',
  },
  wait: {
    label: 'wait',
    dot: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.7)]',
    text: 'text-amber-300',
  },
  escalate: {
    label: 'esc',
    dot: 'bg-rose-400 shadow-[0_0_6px_rgba(251,113,133,0.7)]',
    text: 'text-rose-300',
  },
  error: {
    label: 'error',
    dot: 'bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.7)]',
    text: 'text-rose-400',
  },
}

const DEFAULT_CONFIG = TYPE_CONFIG.think

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

export default function AgentFeed({ campaignId }: { campaignId: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [loadedHistory, setLoadedHistory] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    getActions(campaignId)
      .then((actions) => {
        if (cancelled) return
        setEvents(actions)
        setLoadedHistory(true)
      })
      .catch(() => {
        if (!cancelled) setLoadedHistory(true)
      })
    return () => {
      cancelled = true
    }
  }, [campaignId])

  useEffect(() => {
    if (!campaignId || !loadedHistory) return
    const es = streamEvents(campaignId, (event) => {
      setEvents((prev) => [...prev, event])
    })
    return () => es.close()
  }, [campaignId, loadedHistory])

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [events.length])

  return (
    <div
      ref={containerRef}
      className="relative max-h-[28rem] overflow-y-auto pr-1"
    >
      {events.length === 0 && (
        <p className="text-sm text-neutral-500 font-mono">
          {loadedHistory ? '> awaiting agent…' : '> loading history…'}
        </p>
      )}

      {events.length > 0 && (
        <div
          className="absolute left-[5.25rem] top-1 bottom-1 w-px bg-gradient-to-b from-transparent via-neutral-800 to-transparent"
          aria-hidden
        />
      )}

      <ol className="flex flex-col">
        {events.map((ev, i) => {
          const config = TYPE_CONFIG[ev.type] ?? DEFAULT_CONFIG
          const isLast = i === events.length - 1
          return (
            <li
              key={i}
              className="relative grid grid-cols-[5rem_1.25rem_1fr] gap-x-2 py-2 group"
            >
              <span className="text-[10.5px] font-mono text-neutral-600 tabular-nums pt-[3px] text-right select-none">
                {formatTime(ev.time)}
              </span>

              <span className="relative flex justify-center pt-[7px]">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${config.dot} ${
                    isLast ? 'animate-pulse' : ''
                  }`}
                />
              </span>

              <div className="min-w-0 pb-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span
                    className={`text-[10px] font-mono uppercase tracking-[0.14em] ${config.text}`}
                  >
                    {config.label}
                  </span>
                  {ev.channel && (
                    <span className="text-[10px] font-mono text-neutral-600 uppercase tracking-[0.12em]">
                      · {ev.channel}
                    </span>
                  )}
                </div>
                <p className="text-[13px] text-neutral-200 leading-snug break-words mt-0.5">
                  {ev.action}
                </p>
                {ev.reasoning && (
                  <p className="mt-1 text-[12px] text-neutral-500 leading-relaxed break-words">
                    {ev.reasoning}
                  </p>
                )}
                {ev.type === 'preview' && ev.preview?.body_local && (
                  <div className="mt-2 rounded-md border border-fuchsia-900/60 bg-fuchsia-950/20 px-2.5 py-2">
                    {ev.preview.subject && (
                      <p className="text-[11px] font-mono uppercase tracking-wider text-fuchsia-400 mb-1">
                        subj: {ev.preview.subject}
                      </p>
                    )}
                    <p className="text-[12.5px] text-fuchsia-50 leading-snug whitespace-pre-wrap break-words">
                      {ev.preview.body_local}
                    </p>
                    {ev.preview.english_gloss && (
                      <p className="mt-1.5 text-[11px] text-neutral-500 italic leading-snug">
                        ↳ {ev.preview.english_gloss}
                      </p>
                    )}
                    {ev.preview.target_url && (
                      <a
                        href={ev.preview.target_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1.5 inline-block text-[10.5px] font-mono text-fuchsia-400 hover:text-fuchsia-300 truncate max-w-full"
                      >
                        ↗ {ev.preview.target_url}
                      </a>
                    )}
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
