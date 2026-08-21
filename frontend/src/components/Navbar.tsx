import { useCallback, useEffect, useState } from 'react'
import { clsx } from 'clsx'
import { NavLink, useLocation } from 'react-router-dom'
import { Menu, X, Train, Search, type LucideIcon } from 'lucide-react'

export const ROUTES = {
  TRAIN_SEARCH: '/train-search',
  SEAT_FINDER: '/seat-finder',
} as const

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

export const NAV: readonly NavItem[] = [
  { to: ROUTES.TRAIN_SEARCH, label: 'Train Search', icon: Train },
  { to: ROUTES.SEAT_FINDER, label: 'Seat Finder', icon: Search },
] as const

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  // Close mobile menu whenever the route changes
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  // Close on Escape key
  useEffect(() => {
    if (!menuOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [menuOpen])

  // Prevent body scroll when menu is open on mobile
  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [menuOpen])

  const toggleMenu = useCallback(() => setMenuOpen((o) => !o), [])

  return (
    <>
      {/* ── Top accent stripe ─────────────────────────────────────────── */}
      <div className="h-1 bg-gradient-to-r from-signal-amber via-signal-amber-deep to-signal-amber" />

      <header className="relative z-30 bg-rail-950 text-paper-50 shadow-lg shadow-rail-950/20">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:max-w-6xl sm:px-8 sm:py-5">
          {/* ── Brand ──────────────────────────────────────────────────── */}
          <NavLink
            to={ROUTES.TRAIN_SEARCH}
            className="group flex items-center gap-2.5 transition-opacity hover:opacity-90 sm:gap-3"
          >
            {/* Decorative amber rail mark */}
            <span
              className="h-6 w-1 shrink-0 rounded-full bg-gradient-to-b from-signal-amber to-signal-amber-deep sm:h-7"
              aria-hidden="true"
            />
            <span className="font-display text-2xl font-bold tracking-tight sm:text-[1.65rem]">
              FindMeASeat
              <span className="inline-block text-signal-amber transition-transform group-hover:scale-110">
                .
              </span>
            </span>
          </NavLink>

          {/* ── Desktop nav ────────────────────────────────────────────── */}
          <nav
            aria-label="Main navigation"
            className="hidden items-center gap-2 sm:flex"
          >
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  clsx(
                    'group relative flex items-center gap-2 rounded-full px-5 py-2.5 font-ticket text-xs uppercase tracking-widest transition-all duration-200',
                    isActive
                      ? 'bg-signal-amber/15 text-signal-amber-bright ring-1 ring-inset ring-signal-amber/20'
                      : 'text-paper-50/60 hover:bg-paper-50/10 hover:text-paper-50',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <n.icon
                      size={16}
                      className={clsx(
                        'transition-colors',
                        isActive
                          ? 'text-signal-amber'
                          : 'text-paper-50/40 group-hover:text-paper-50/70',
                      )}
                    />
                    {n.label}
                    {/* Active indicator bar */}
                    {isActive && (
                      <span className="absolute -bottom-2.5 left-1/2 h-0.5 w-8 -translate-x-1/2 rounded-full bg-gradient-to-r from-signal-amber/60 via-signal-amber to-signal-amber/60" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          {/* ── Mobile hamburger button ────────────────────────────────── */}
          <button
            type="button"
            onClick={toggleMenu}
            aria-expanded={menuOpen}
            aria-controls="mobile-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className={clsx(
              'relative z-40 flex items-center justify-center rounded-lg p-2 transition-all duration-200 sm:hidden',
              menuOpen
                ? 'bg-paper-50/10 text-signal-amber'
                : 'text-paper-50/70 hover:bg-paper-50/5 hover:text-paper-50',
            )}
          >
            <span className="relative h-5 w-5">
              <Menu
                size={20}
                className={clsx(
                  'absolute inset-0 transition-all duration-300',
                  menuOpen
                    ? 'rotate-90 scale-0 opacity-0'
                    : 'rotate-0 scale-100 opacity-100',
                )}
              />
              <X
                size={20}
                className={clsx(
                  'absolute inset-0 transition-all duration-300',
                  menuOpen
                    ? 'rotate-0 scale-100 opacity-100'
                    : '-rotate-90 scale-0 opacity-0',
                )}
              />
            </span>
          </button>
        </div>

        {/* ── Gradient bottom accent — desktop only ───────────────────── */}
        <div
          className="hidden h-px bg-gradient-to-r from-transparent via-signal-amber/30 to-transparent sm:block"
          aria-hidden="true"
        />

        {/* ── Mobile menu panel ──────────────────────────────────────── */}
        <div
          id="mobile-menu"
          className={clsx(
            'overflow-hidden border-t border-paper-50/10 sm:hidden',
            'transition-all duration-300 ease-in-out',
            menuOpen ? 'max-h-60 opacity-100' : 'max-h-0 opacity-0',
          )}
        >
          <nav
            aria-label="Mobile navigation"
            className="mx-auto max-w-5xl space-y-1 px-4 py-3"
          >
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 rounded-lg px-3.5 py-3 font-ticket text-sm uppercase tracking-widest transition-all duration-200',
                    isActive
                      ? 'bg-signal-amber/15 text-signal-amber-bright'
                      : 'text-paper-50/70 active:bg-paper-50/10 hover:bg-paper-50/5 hover:text-paper-50',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <n.icon
                      size={18}
                      className={clsx(
                        'shrink-0 transition-colors',
                        isActive ? 'text-signal-amber' : 'text-paper-50/40',
                      )}
                    />
                    <span>{n.label}</span>
                    {isActive && (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-signal-amber" />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* ── Backdrop overlay for mobile menu ─────────────────────────── */}
      <div
        className={clsx(
          'fixed inset-0 z-20 bg-rail-950/50 backdrop-blur-sm transition-opacity duration-200 sm:hidden',
          menuOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={() => setMenuOpen(false)}
        aria-hidden="true"
      />
    </>
  )
}
