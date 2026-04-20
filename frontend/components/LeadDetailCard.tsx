import type { Lead } from '@/lib/types'

const PLATFORM_BADGE: Record<string, string> = {
  linkedin: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  reddit: 'bg-orange-500/10 text-orange-300 border-orange-500/30',
  youtube: 'bg-red-600/10 text-red-400 border-red-600/30',
  tiktok: 'bg-neutral-500/10 text-neutral-300 border-neutral-500/30',
  naver: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  quora: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
  zhihu: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  weibo: 'bg-red-500/10 text-red-300 border-red-500/30',
  xiaohongshu: 'bg-pink-500/10 text-pink-300 border-pink-500/30',
}

const STATUS_BADGE: Record<string, string> = {
  identified: 'bg-neutral-800 text-neutral-400 border-neutral-700',
  contacted: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  replied: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  meeting: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
}

export default function LeadDetailCard({ lead }: { lead: Lead }) {
  const platform = (lead.platform || 'linkedin').toLowerCase()
  const platformBadge = PLATFORM_BADGE[platform] || PLATFORM_BADGE.linkedin
  const statusBadge = STATUS_BADGE[lead.status] || STATUS_BADGE.identified

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5 backdrop-blur-sm hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span
              className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${platformBadge}`}
            >
              {platform}
            </span>
            <span
              className={`text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded-full border ${statusBadge}`}
            >
              {lead.status}
            </span>
          </div>
          <h2 className="text-lg font-medium text-neutral-100 tracking-tight">
            {lead.name}
          </h2>
          {(lead.title || lead.company) && (
            <p className="text-[12px] text-neutral-400 mt-0.5">
              {lead.title}
              {lead.title && lead.company ? ' · ' : ''}
              {lead.company}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-3">
        {lead.linkedin_url && (
          <a
            href={lead.linkedin_url}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-mono text-sky-400 hover:text-sky-300 transition-colors"
          >
            ↗ LinkedIn
          </a>
        )}
        {lead.source_post_url && (
          <a
            href={lead.source_post_url}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-mono text-neutral-400 hover:text-neutral-200 transition-colors truncate max-w-full"
          >
            ↗ source post
          </a>
        )}
      </div>

      {lead.source_comment_text && (
        <div className="rounded-lg bg-neutral-950/60 border border-neutral-800 px-3 py-2.5 mb-2">
          <p className="text-[10px] font-mono uppercase text-neutral-600 mb-1.5">
            they said
          </p>
          <p className="text-[13px] text-neutral-200 leading-relaxed whitespace-pre-wrap">
            {lead.source_comment_text}
          </p>
        </div>
      )}

      {lead.reply_text && (
        <div className="rounded-lg bg-emerald-950/30 border border-emerald-900/40 px-3 py-2.5">
          <p className="text-[10px] font-mono uppercase text-emerald-400/80 mb-1.5">
            we sent {lead.reply_language ? `· ${lead.reply_language}` : ''}
          </p>
          <p className="text-[13px] text-emerald-100/90 leading-relaxed whitespace-pre-wrap">
            {lead.reply_text}
          </p>
        </div>
      )}
    </div>
  )
}
