'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { deployCampaign, getApifyHealth, getCountries } from '@/lib/api'
import type { Country } from '@/lib/types'

const FALLBACK_COUNTRIES: Country[] = [
  { name: 'South Korea', language: 'ko', language_name: 'Korean' },
  { name: 'Japan', language: 'ja', language_name: 'Japanese' },
  { name: 'India', language: 'en', language_name: 'English' },
  { name: 'China', language: 'zh', language_name: 'Simplified Chinese' },
  { name: 'Germany', language: 'de', language_name: 'German' },
  { name: 'Singapore', language: 'en', language_name: 'English' },
  { name: 'United States', language: 'en', language_name: 'English' },
  { name: 'Brazil', language: 'pt', language_name: 'Brazilian Portuguese' },
]

export default function DeployForm() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [countries, setCountries] = useState<Country[]>(FALLBACK_COUNTRIES)
  const [apifyOk, setApifyOk] = useState<boolean | null>(null)
  const [form, setForm] = useState({
    company_url: '',
    country: 'South Korea',
  })

  useEffect(() => {
    getCountries()
      .then((c) => {
        if (Array.isArray(c) && c.length > 0) setCountries(c)
      })
      .catch(() => {})
    getApifyHealth()
      .then((r) => setApifyOk(r.ok))
      .catch(() => setApifyOk(false))
  }, [])

  const handleDeploy = async () => {
    if (!form.company_url) return
    setLoading(true)
    setError(null)
    try {
      const result = await deployCampaign(form)
      router.push(`/dashboard/${result.campaign_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deploy failed')
    } finally {
      setLoading(false)
    }
  }

  const canDeploy = !!form.company_url && !loading
  const selectedLanguage = countries.find((c) => c.name === form.country)
    ?.language_name

  return (
    <div className="relative rounded-2xl bg-neutral-900/80 border border-neutral-800 backdrop-blur-sm p-6 max-w-xl mx-auto shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_20px_60px_-20px_rgba(0,0,0,0.6)]">
      <div className="absolute inset-0 rounded-2xl pointer-events-none bg-gradient-to-b from-white/[0.02] to-transparent" />

      <div className="relative">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-500 font-mono">
            Deploy global agent
          </span>
        </div>
        <h2 className="text-lg font-medium text-neutral-100 tracking-tight">
          One URL. One country. Two parallel streams.
        </h2>
        <p className="text-sm text-neutral-500 mt-1">
          The agent reads your site, then in {selectedLanguage ?? 'the local language'} it
          replies to people on social and pitches event organizers / press.
        </p>

        <div className="flex flex-col gap-4 mt-6">
          <div>
            <label className="text-[11px] uppercase tracking-[0.14em] text-neutral-500 font-mono mb-1.5 block">
              Company URL
            </label>
            <div className="relative group">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm font-mono select-none">
                ↗
              </span>
              <input
                className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-3 py-3 text-sm text-neutral-100 placeholder-neutral-600 outline-none focus:border-neutral-600 focus:ring-1 focus:ring-neutral-700 transition-all"
                placeholder="https://yourcompany.com"
                value={form.company_url}
                onChange={(e) =>
                  setForm((f) => ({ ...f, company_url: e.target.value }))
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canDeploy) handleDeploy()
                }}
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] uppercase tracking-[0.14em] text-neutral-500 font-mono mb-1.5 block">
              Target country
            </label>
            <div className="relative">
              <select
                className="w-full appearance-none bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-3 text-sm text-neutral-100 outline-none focus:border-neutral-600 focus:ring-1 focus:ring-neutral-700 transition-all cursor-pointer"
                value={form.country}
                onChange={(e) =>
                  setForm((f) => ({ ...f, country: e.target.value }))
                }
              >
                {countries.map((c) => (
                  <option key={c.name} value={c.name} className="bg-neutral-900">
                    {c.name} — {c.language_name}
                  </option>
                ))}
              </select>
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 text-xs pointer-events-none">
                ▾
              </span>
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/40 border border-red-900/60 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            onClick={handleDeploy}
            disabled={!canDeploy}
            className="group relative w-full bg-emerald-500 hover:bg-emerald-400 disabled:bg-neutral-800 disabled:text-neutral-500 disabled:cursor-not-allowed text-neutral-950 disabled:hover:bg-neutral-800 rounded-lg py-3 text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="inline-block h-3 w-3 rounded-full border-2 border-neutral-950/30 border-t-neutral-950 animate-spin" />
                Deploying agent
              </>
            ) : (
              <>
                Deploy agent
                <span className="transition-transform group-hover:translate-x-0.5">
                  →
                </span>
              </>
            )}
          </button>

          <div className="flex items-center justify-between text-[11px] text-neutral-600 font-mono">
            <span>agent runs 24/7 · pause anytime</span>
            <span className="flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  apifyOk === null
                    ? 'bg-neutral-600'
                    : apifyOk
                      ? 'bg-emerald-400'
                      : 'bg-rose-400'
                }`}
              />
              apify {apifyOk === null ? 'checking' : apifyOk ? 'ok' : 'auth fail'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
