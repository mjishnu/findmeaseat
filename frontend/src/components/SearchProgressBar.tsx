import { CheckCircle2, Loader2, Sparkles } from 'lucide-react'
import type { ManifestProgress } from '../api'

interface SearchProgressBarProps {
  progress: ManifestProgress | null
}

const STEPS = [
  { id: 1, label: 'Checking Routes' },
  { id: 2, label: 'Verifying Availability' },
] as const

export function SearchProgressBar({ progress }: SearchProgressBarProps) {
  if (!progress) return null

  const currentStep = progress.currentPhaseStep ?? (progress.percent > 90 ? 2 : 1)
  const isComplete = progress.phase === 'complete' || progress.percent >= 100

  return (
    <div
      role="progressbar"
      aria-valuenow={progress.percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={`${progress.label} - ${progress.percent}% complete`}
      className="mt-6 rounded-2xl border border-rail-900/12 bg-paper-50 p-4 shadow-sm transition-all duration-200 sm:p-5"
    >
      {/* Header: Live action label & percentage */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-rail-900/5 text-rail-900">
            {isComplete ? (
              <CheckCircle2 className="h-4 w-4 text-signal-green-deep" />
            ) : (
              <Loader2 className="h-4 w-4 animate-spin text-rail-700" />
            )}
          </span>
          <div>
            <h2 className="text-sm font-semibold text-rail-950 sm:text-base">
              {progress.label}
            </h2>
            {progress.subLabel && (
              <p className="font-ticket text-xs text-rail-700">
                {progress.subLabel}
              </p>
            )}
          </div>
        </div>

        {/* Monospace percentage pill */}
        <div className="inline-flex items-center rounded-lg border border-rail-900/10 bg-paper-100 px-2.5 py-1 font-ticket text-xs font-bold text-rail-900 sm:text-sm">
          {progress.percent}%
        </div>
      </div>

      {/* Progress Bar Track */}
      <div className="mt-3.5 h-2.5 w-full overflow-hidden rounded-full bg-paper-200/90 sm:h-3">
        <div
          className="h-full rounded-full bg-rail-900 transition-all duration-300 ease-out"
          style={{ width: `${Math.max(5, Math.min(100, progress.percent))}%` }}
        />
      </div>

      {/* Step Pills */}
      <div className="mt-3.5 grid grid-cols-2 gap-2.5 border-t border-rail-900/10 pt-3">
        {STEPS.map((step) => {
          const isDone = isComplete || currentStep > step.id
          const isActive = !isComplete && currentStep === step.id

          return (
            <div
              key={step.id}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-center font-ticket text-[11px] sm:text-xs transition-colors ${isDone
                  ? 'bg-signal-green/10 text-signal-green-deep font-semibold'
                  : isActive
                    ? 'bg-rail-900/10 text-rail-950 font-bold ring-1 ring-rail-900/20'
                    : 'bg-paper-100/60 text-rail-700/60'
                }`}
            >
              {isDone ? (
                <CheckCircle2 className="h-3 w-3 shrink-0 text-signal-green-deep" />
              ) : isActive ? (
                <Sparkles className="h-3 w-3 shrink-0 text-rail-700 animate-pulse" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-rail-700/30" />
              )}
              <span className="truncate">{step.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
