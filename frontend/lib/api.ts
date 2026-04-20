import type {
  AgentEvent,
  Campaign,
  CompanySignal,
  Country,
  Lead,
  Stats,
} from './types'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function deployCampaign(data: {
  company_url: string
  country: string
}): Promise<{ campaign_id: string; status: string; country: string }> {
  const res = await fetch(`${BASE}/deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Deploy failed: ${res.status}`)
  return res.json()
}

export async function getCountries(): Promise<Country[]> {
  const res = await fetch(`${BASE}/countries`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`getCountries failed: ${res.status}`)
  return res.json()
}

export async function getCampaigns(): Promise<Campaign[]> {
  const res = await fetch(`${BASE}/campaigns`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`getCampaigns failed: ${res.status}`)
  return res.json()
}

export async function getCampaign(campaignId: string): Promise<Campaign> {
  const res = await fetch(`${BASE}/campaign/${campaignId}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`getCampaign failed: ${res.status}`)
  return res.json()
}

export async function getLeads(campaignId: string): Promise<Lead[]> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/leads`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`getLeads failed: ${res.status}`)
  return res.json()
}

export async function getSignals(
  campaignId: string,
): Promise<CompanySignal[]> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/signals`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`getSignals failed: ${res.status}`)
  return res.json()
}

export async function getStats(campaignId: string): Promise<Stats> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/stats`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`getStats failed: ${res.status}`)
  return res.json()
}

export async function getActions(campaignId: string): Promise<AgentEvent[]> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/actions`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error(`getActions failed: ${res.status}`)
  return res.json()
}

export async function pauseCampaign(
  campaignId: string,
): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/pause`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`pauseCampaign failed: ${res.status}`)
  return res.json()
}

export async function deleteCampaign(
  campaignId: string,
): Promise<{ status: string; campaign_id: string }> {
  const res = await fetch(`${BASE}/campaign/${campaignId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`deleteCampaign failed: ${res.status}`)
  return res.json()
}

export async function updateCampaignSettings(
  campaignId: string,
  settings: { require_human_approval: boolean },
): Promise<{ require_human_approval: boolean }> {
  const res = await fetch(`${BASE}/campaign/${campaignId}/settings`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!res.ok) throw new Error(`updateCampaignSettings failed: ${res.status}`)
  return res.json()
}

export async function approveAction(
  campaignId: string,
  approvalId: string,
): Promise<{ status: string }> {
  const res = await fetch(
    `${BASE}/campaign/${campaignId}/approve/${approvalId}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`approveAction failed: ${res.status}`)
  return res.json()
}

export async function rejectAction(
  campaignId: string,
  approvalId: string,
): Promise<{ status: string }> {
  const res = await fetch(
    `${BASE}/campaign/${campaignId}/reject/${approvalId}`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`rejectAction failed: ${res.status}`)
  return res.json()
}

export async function sendGmailLead(
  campaignId: string,
  leadId: number,
): Promise<{ status: string }> {
  const res = await fetch(
    `${BASE}/campaign/${campaignId}/leads/${leadId}/send-gmail`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`sendGmailLead failed: ${res.status}`)
  return res.json()
}

export async function getApifyHealth(): Promise<{
  ok: boolean
  username?: string
  error?: string
}> {
  const res = await fetch(`${BASE}/healthcheck/apify`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`apify healthcheck failed: ${res.status}`)
  return res.json()
}

/** Open SSE stream for a campaign. Returns the EventSource so callers can close it. */
export function streamEvents(
  campaignId: string,
  onEvent: (event: AgentEvent) => void,
): EventSource {
  const es = new EventSource(`${BASE}/stream/${campaignId}`)
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as AgentEvent
      onEvent(data)
    } catch {
      // ignore malformed payloads
    }
  }
  return es
}
