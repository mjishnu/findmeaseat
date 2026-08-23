export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="mt-auto w-full bg-rail-950 text-paper-50 shadow-lg">
      {/* ── Top amber signal stripe matching the header ───────────── */}
      <div className="h-1 bg-gradient-to-r from-signal-amber via-signal-amber-deep to-signal-amber" />

      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-3 sm:flex-row sm:px-8 sm:py-3.5">
        {/* ── Left / Attribution ────────────────────────────────────── */}
        <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 font-ticket text-xs text-paper-50/70 sm:justify-start">
          <span className="font-medium text-paper-50/90">
            © {currentYear} FindMeASeat
          </span>
          <span className="text-paper-50/30" aria-hidden="true">
            •
          </span>
          <span className="inline-flex items-center gap-1">
            Made with
            <span
              className="inline-block text-signal-red-bright transition-transform duration-200 hover:scale-125 select-none"
              title="Love"
              role="img"
              aria-label="love"
            >
              ❤️
            </span>
            by{' '}
            <a
              href="https://github.com/mjishnu"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-paper-50 underline decoration-signal-amber decoration-1 underline-offset-2 transition-colors hover:text-signal-amber-bright"
            >
              mjishnu
            </a>
          </span>
        </div>

        {/* ── Right / GitHub Repository Link ────────────────────────── */}
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/mjishnu/findmeaseat"
            target="_blank"
            rel="noopener noreferrer"
            className="group flex items-center gap-2 rounded-full bg-paper-50/10 px-3.5 py-1.5 font-ticket text-xs uppercase tracking-widest text-paper-50/80 ring-1 ring-inset ring-paper-50/15 transition-all duration-200 hover:bg-signal-amber/15 hover:text-signal-amber-bright hover:ring-signal-amber/30 active:scale-95"
            aria-label="View source code on GitHub"
          >
            {/* GitHub Octocat Icon */}
            <svg
              viewBox="0 0 24 24"
              width="15"
              height="15"
              fill="currentColor"
              className="transition-transform duration-200 group-hover:scale-110 group-hover:text-signal-amber"
              aria-hidden="true"
            >
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
            <span>GitHub</span>
            <span
              className="inline-block text-signal-amber transition-transform duration-200 group-hover:translate-x-0.5"
              aria-hidden="true"
            >
              →
            </span>
          </a>
        </div>
      </div>
    </footer>
  )
}