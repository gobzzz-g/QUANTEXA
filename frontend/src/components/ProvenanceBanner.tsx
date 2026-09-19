import { AlertCircle } from 'lucide-react'

export default function ProvenanceBanner({ provenance }: { provenance: any }) {
  if (!provenance || provenance.data_source === 'live') return null
  
  return (
    <div className="bg-warning/10 border-l-4 border-warning p-4 rounded-r-lg mb-6 flex items-start space-x-3 shadow-sm backdrop-blur-sm">
      <AlertCircle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
      <div>
        <h3 className="text-warning font-semibold tracking-wide">
          Showing {provenance.data_source} data as of {provenance.last_bar}
        </h3>
        <p className="text-sm text-warning/80 mt-1 font-medium">
          {provenance.instrument_name} ({provenance.ticker}). Fetched at {provenance.fetched_at}.
        </p>
      </div>
    </div>
  )
}
