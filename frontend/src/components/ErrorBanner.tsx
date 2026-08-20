import type { ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'

interface ErrorBannerProps {
  children: ReactNode
}

export function ErrorBanner({ children }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="mt-8 flex items-center justify-center gap-2.5 rounded-lg border border-signal-red/25 bg-signal-red/5 p-6 text-center text-sm text-signal-red"
    >
      <AlertCircle className="size-4 shrink-0" />
      <div>{children}</div>
    </div>
  )
}
