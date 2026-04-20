'use client'

import { useEffect, useMemo, useRef } from 'react'
import type { AgentEvent, AgentEventType, StreamId } from '@/lib/types'

const TYPE_CFG: Record<AgentEventType, { color: string; symbol: string }> = {
  scan:    { color: 'text-sky-400',     symbol: '›' },
  think:   { color: 'text-violet-400',  symbol: '·' },
  act:     { color: 'text-emerald-400', symbol: '▶' },
  preview: { color: 'text-fuchsia-400', symbol: '◎' },
  wait:    { color: 'text-amber-400',   symbol: '⏸' },
  escalate:{ color: 'text-rose-400',    symbol: '⚑' },
  error:   { color: 'text-rose-500',    symbol: '✗' },
}

const CHANNEL_LABEL: Record<string, string> = {
  apify:        'apify',
  llm:          'llm',
  'browser-use':'b-use',
  linkedin:     'li',
  reddit:       'rd',
  youtube:      'yt',
  tiktok:       'tk',
  naver:        'nvr',
  quora:        'qr',
  zhihu:        'zh',
  weibo:        'wb',
  blind:        'bld',
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
  campaignId?: string
  events: AgentEvent[]
  streams: StreamId[]
  loaded?: boolean
  emptyLabel?: string
  cap?: number
  /** When set, only show events for this platform channel (or action text mentioning it). */
  platform?: string
}

export default function PanelActivityFeed({
  campaignId: _campaignId,
  events,
  streams,
  loaded = true,
  emptyLabel = '› awaiting first action…',
  cap = 60,
  platform,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  const allInStreams = useMemo(() => {
    const allow = new Set(streams)
    return events.filter((ev) => allow.has((ev.stream || 'system') as StreamId))
  }, [events, streams])

  const filtered = useMemo(() => {
    if (!platform || platform === 'all') return allInStreams
    const p = platform.toLowerCase()
    return allInStreams.filter(
      (ev) =>
        (ev.channel || '').toLowerCase() === p ||
        (ev.action || '').toLowerCase().includes(p),
    )
  }, [allInStreams, platform])

  useEffect(() => {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [filtered.length])

  const visible = filtered.slice(-cap)
  const isLive = loaded && visible.length > 0

  return (
    <div className="flex flex-col min-h-0 flex-1 rounded-lg border border-neutral-800/60 bg-[#080a0a] overflow-hidden">

      {/* Log area */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-y-auto px-3 py-2.5 font-mono text-[11px]"
      >
        {!loaded && (
          <div className="flex gap-1.5 text-neutral-600 leading-relaxed">
            <span className="w-[5.5rem] shrink-0 text-right tabular-nums select-none">--:--:--</span>
            <span className="text-neutral-700 select-none">›</span>
            <span className="animate-pulse text-neutral-500">loading…</span>
          </div>
        )}

        {loaded && visible.length === 0 && (
          <div className="flex gap-1.5 text-neutral-600 leading-relaxed">
            <span className="w-[5.5rem] shrink-0 text-right tabular-nums select-none">--:--:--</span>
            <span className="text-neutral-700 select-none">›</span>
            <span>
              {platform && platform !== 'all' && allInStreams.length > 0
                ? `no ${platform} activity yet — agent is running on other channels`
                : emptyLabel.replace(/^[›>]\s*/, '')}
            </span>
          </div>
        )}

        {loaded && visible.map((ev, i) => {
          const cfg = TYPE_CFG[ev.type] ?? TYPE_CFG.scan
          const channel = ev.channel ? (CHANNEL_LABEL[ev.channel] || ev.channel) : ''

          return (
            <div key={`${ev.time || 'evt'}-${i}`} className="animate-log-entry mb-2">
              {/* Main log line */}
              <div className="flex gap-1.5 items-baseline leading-relaxed">
                <span className="text-neutral-700 w-[5.5rem] shrink-0 text-right tabular-nums select-none">
                  {formatTime(ev.time)}
                </span>
                <span className={`${cfg.color} shrink-0 select-none w-3 text-center`}>
                  {cfg.symbol}
                </span>
                {channel && (
                  <span className="text-neutral-600 shrink-0 uppercase text-[9px] tracking-widest leading-[1.6]">
                    {channel}
                  </span>
                )}
                <span className="text-neutral-200 break-words flex-1 leading-relaxed">
                  {ev.action}
                </span>
                {ev.live_url && (
                  <a
                    href={ev.live_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-1 text-emerald-400 hover:text-emerald-300 shrink-0"
                  >
                    ↗
                  </a>
                )}
              </div>

              {/* Reasoning (indented, dimmer) */}
              {ev.reasoning && (
                <div className="flex gap-1.5 items-baseline mt-0.5">
                  <span className="w-[5.5rem] shrink-0 select-none" />
                  <span className="w-3 shrink-0 select-none" />
                  {channel && (
                    <span className="text-[9px] uppercase tracking-widest opacity-0 select-none shrink-0">
                      {channel}
                    </span>
                  )}
                  <span className="text-neutral-600 break-words flex-1 text-[10.5px] leading-snug line-clamp-2">
                    {ev.reasoning}
                  </span>
                </div>
              )}

              {/* Approval type: preview with message body */}
              {ev.type === 'preview' && ev.preview?.body_local && (
                <div className="mt-1.5 ml-[6.5rem] rounded border border-fuchsia-900/30 bg-fuchsia-950/15 px-2 py-1.5">
                  {ev.preview.subject && (
                    <p className="text-[9px] text-fuchsia-400/80 uppercase tracking-widest mb-1">
                      subj: {ev.preview.subject}
                    </p>
                  )}
                  <p className="text-[11px] text-fuchsia-100/90 whitespace-pre-wrap break-words leading-snug">
                    {ev.preview.body_local}
                  </p>
                  {ev.preview.english_gloss && (
                    <p className="mt-1 text-[10px] text-neutral-500 italic">
                      ↳ {ev.preview.english_gloss}
                    </p>
                  )}
                  {ev.preview.target_url && (
                    <a
                      href={ev.preview.target_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block text-[10px] text-fuchsia-400 hover:text-fuchsia-300 truncate max-w-full"
                    >
                      ↗ {ev.preview.target_url}
                    </a>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* Blinking cursor */}
        {loaded && (
          <div className="flex gap-1.5 items-center mt-0.5 h-4">
            <span className="w-[5.5rem] shrink-0 select-none" />
            <span className="text-emerald-400/70 terminal-cursor text-[13px] leading-none select-none">
              ▋
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
