export function SkeletonResults() {
  return (
    <div className="mt-10 space-y-5" aria-hidden>
      <div className="h-12 animate-pulse rounded-lg bg-rail-200/50" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/50 md:col-span-2" />
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/40" />
        <div className="h-64 animate-pulse rounded-xl bg-rail-200/40" />
      </div>
    </div>
  )
}
