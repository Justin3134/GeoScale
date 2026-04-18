'use client'

import { useEffect, useMemo, useRef } from 'react'
import type { AgentEvent, AgentEventType, StreamId } from '@/lib/types'

const TYPE_DOT: Record<AgentEventType, string> = {
  scan: 'bg-sky-400',
  think: 'bg-violet-400',
  act: 'bg-emerald-400',
  preview: 'bg-fuchsia-400',
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

interface Props {
  events: AgentEvent[]
  streams: StreamId[]
  loaded?: boolean
  emptyLabel?: string
  cap?: number
}

export default function PanelActivityStrip({
  events,
  streams,
  loaded = true,
  emptyLabel = '› awaiting first action…',
  cap = 30,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    const allow = new Set(streams)
    return events.filter((ev) => allow.has((ev.stream || 'system') as StreamId))
  }, [events, streams])

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [filtered.length])

  const visible = filtered.slice(-cap)

  return (
    <div
      ref={containerRef}
      className="flex flex-row gap-1.5 overflow-x-auto pb-1 mb-3 scrollbar-thin scrollbar-thumb-neutral-800"
    >
      {!loaded && (
        <span className="text-[10px] font-mono text-neutral-600 px-2 py-1">
          › loading…
        </span>
      )}
      {loaded && visible.length === 0 && (
        <span className="text-[10px] font-mono text-neutral-600 px-2 py-1">
          {emptyLabel}
        </span>
      )}
      {visible.map((ev, i) => {
        const dot = TYPE_DOT[ev.type] || 'bg-neutral-500'
        const channel = ev.channel
          ? CHANNEL_LABEL[ev.channel] || ev.channel
          : ''
        return (
          <div
            key={`${ev.time || 'evt'}-${i}`}
            className="shrink-0 max-w-[16rem] rounded-md border border-neutral-800 bg-neutral-950/60 px-2 py-1"
            title={ev.reasoning || ev.action}
          >
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${dot}`} aria-hidden />
              <span className="text-[9px] font-mono uppercase tracking-wider text-neutral-600">
                {formatTime(ev.time)}
              </span>
              {channel && (
                <span className="text-[9px] font-mono uppercase tracking-wider text-neutral-500">
                  {channel}
                </span>
              )}
              <span className="text-[10.5px] text-neutral-200 leading-tight truncate max-w-[10rem]">
                {ev.action}
              </span>
              {ev.live_url && (
                <a
                  href={ev.live_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[9px] font-mono text-emerald-400 hover:text-emerald-300 shrink-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  ↗
                </a>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
