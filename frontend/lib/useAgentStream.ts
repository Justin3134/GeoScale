'use client'

import { useEffect, useState } from 'react'
import { getActions, streamEvents } from './api'
import type { AgentEvent } from './types'

/** Hydrate from DB then tail SSE. Shared by every stream panel. */
export function useAgentStream(campaignId: string | undefined) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!campaignId) return
    let cancelled = false
    getActions(campaignId)
      .then((actions) => {
        if (cancelled) return
        setEvents(actions)
        setLoaded(true)
      })
      .catch(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [campaignId])

  useEffect(() => {
    if (!campaignId || !loaded) return
    const es = streamEvents(campaignId, (event) => {
      setEvents((prev) => [...prev, event])
    })
    return () => es.close()
  }, [campaignId, loaded])

  return { events, loaded }
}
