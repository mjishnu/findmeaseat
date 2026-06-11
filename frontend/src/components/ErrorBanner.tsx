interface ErrorBannerProps {
  message: string
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <p
      role="alert"
      className="mt-10 rounded-lg border border-signal-red/40 bg-signal-red/10 px-4 py-3 text-sm text-signal-red"
    >
      {message}
    </p>
  )
}
