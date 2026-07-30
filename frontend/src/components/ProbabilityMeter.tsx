interface ProbabilityMeterProps {
  probability: number // 0..1, or -1 when confirmtkt has no estimate
}

export function ProbabilityMeter({ probability }: ProbabilityMeterProps) {
  if (probability < 0) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-rail-200/60" />
        <span className="font-ticket text-sm font-medium text-rail-500">No estimate</span>
      </div>
    )
  }
  const pct = Math.round(probability * 100)
  const tone = pct >= 75 ? 'bg-signal-green' : pct >= 40 ? 'bg-signal-amber' : 'bg-signal-red'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-rail-200/60">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-ticket text-sm font-medium text-rail-900">{pct}%</span>
    </div>
  )
}
