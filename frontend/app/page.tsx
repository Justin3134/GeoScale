import CampaignsList from '@/components/CampaignsList'
import DeployForm from '@/components/DeployForm'

export default function Home() {
  return (
    <main className="relative min-h-screen bg-neutral-950 text-neutral-100 overflow-hidden">
      <div className="absolute inset-0 bg-spotlight pointer-events-none" />
      <div className="absolute inset-0 bg-grid pointer-events-none" />

      <div className="relative w-full max-w-2xl mx-auto px-6 py-20">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-neutral-800 bg-neutral-900/60 backdrop-blur-sm mb-5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[11px] uppercase tracking-[0.18em] text-neutral-400 font-mono">
              Autonomous GTM agent
            </span>
          </div>
          <h1 className="text-5xl font-medium tracking-tight bg-gradient-to-b from-white to-neutral-400 bg-clip-text text-transparent mb-4">
            GeoScale
          </h1>
          <p className="text-neutral-400 text-base max-w-md mx-auto leading-relaxed">
            Drop your URL. Pick a market. The agent reads your site, finds
            your buyers, and runs outreach 24/7.
          </p>
        </div>

        <DeployForm />
        <CampaignsList />

        <div className="text-center text-[11px] text-neutral-600 font-mono mt-12">
          Built for founders entering new markets
        </div>
      </div>
    </main>
  )
}
