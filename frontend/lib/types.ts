export type CampaignStatus = 'running' | 'paused' | 'meeting_booked'

export type AgentEventType =
  | 'scan'
  | 'think'
  | 'act'
  | 'preview'
  | 'wait'
  | 'escalate'
  | 'error'

export interface AgentEventPreview {
  target_name?: string
  target_url?: string
  platform?: string
  subject?: string
  body_local?: string
  english_gloss?: string
  signal_text?: string
  signal_type?: string
  approval_id?: string | null
}

export type StreamId = 'people' | 'opportunities' | 'signals' | 'system'

export type SignalType = 'funding' | 'hiring' | 'engagement'

export type SignalStatus = 'new' | 'resolved' | 'contacted' | 'skipped'

export type LeadStatus = 'identified' | 'contacted' | 'replied' | 'meeting'

export type OpportunityStatus =
  | 'identified'
  | 'contacted'
  | 'replied'
  | 'booked'

export type OpportunityType =
  | 'hackathon'
  | 'event'
  | 'accelerator'
  | 'press'
  | 'community'
  | 'vc'

export interface Country {
  name: string
  language: string
  language_name: string
}

export interface Campaign {
  id: string
  country: string
  language?: string
  goal: string
  company_url?: string
  status: CampaignStatus
  require_human_approval?: boolean
  created_at?: string
  total_leads?: number
  contacted?: number
  replied?: number
  meetings?: number
  total_opportunities?: number
  opportunities_contacted?: number
  total_signals?: number
  signals_contacted?: number
  total_actions?: number
}

export interface AgentEvent {
  type: AgentEventType
  stream?: StreamId
  action: string
  reasoning?: string
  channel?: string | null
  lead?: string
  live_url?: string | null
  session_ended?: boolean
  preview?: AgentEventPreview | null
  time?: string
}

export interface Lead {
  name: string
  title: string
  company: string
  score: number
  status: LeadStatus
  platform?: string
  source_post_url?: string | null
  source_comment_text?: string | null
  reply_text?: string | null
  reply_language?: string | null
  linkedin_url?: string | null
}

export interface Opportunity {
  id: number
  type: OpportunityType
  title: string
  description?: string | null
  url: string
  contact_url?: string | null
  contact_email?: string | null
  score: number
  status: OpportunityStatus
  pitch_text?: string | null
  pitch_language?: string | null
}

export interface CompanySignal {
  id: number
  type: SignalType
  company_name: string
  signal_text: string
  signal_url?: string | null
  suggested_role?: string | null
  status: SignalStatus
  resolved_lead_url?: string | null
  created_at?: string | null
}

export interface Stats {
  total_leads: number
  contacted: number
  replied: number
  meetings: number
  total_opportunities: number
  opportunities_contacted: number
  total_signals?: number
  signals_contacted?: number
  total_actions: number
}
