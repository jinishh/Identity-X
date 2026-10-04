import { useQuery } from '@tanstack/react-query'
import { DropdownMenu as DM } from 'radix-ui'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router'
import { api, unwrap } from '@/api/client'
import { BookCheck, KeyRound, Lock, LogOut, Search } from '@/components/icons'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/cn'
import { ROLE_LABEL, fmtRelative, shortHash } from '@/lib/format'
import { Avatar } from './domain'
import { Logo } from './Logo'
import { Spinner, Tip } from './ui'

type Item = { to: string; label: string; roles?: string[]; badge?: 'inbox' | 'alerts' }

const CASE_ROLES = ['INVESTIGATOR', 'SUPERVISOR', 'PROSECUTOR', 'FORENSIC_EXPERT']
const NAV: Item[] = [
  { to: '/', label: 'Docket' },
  { to: '/cases', label: 'Cases', roles: [...CASE_ROLES, 'AUDITOR'] },
  { to: '/inbox', label: 'Approvals', roles: CASE_ROLES, badge: 'inbox' },
  { to: '/shared', label: 'Shared with me', roles: CASE_ROLES },
  { to: '/audit', label: 'Ledger', roles: ['AUDITOR', 'SUPERVISOR'] },
  { to: '/alerts', label: 'Alerts', roles: ['AUDITOR', 'SUPERVISOR'], badge: 'alerts' },
  { to: '/admin/users', label: 'Accounts', roles: ['SUPER_ADMIN', 'ADMIN'] },
  { to: '/demo', label: 'Tamper lab', roles: ['SUPER_ADMIN'] },
]

function useBadges(role?: string) {
  const inbox = useQuery({
    queryKey: ['requests', 'inbox', 'PENDING'],
    queryFn: () => unwrap(api.GET('/requests', { params: { query: { box: 'inbox', status: 'PENDING' } } })),
    enabled: !!role && CASE_ROLES.includes(role),
    refetchInterval: 15_000,
  })
  const alerts = useQuery({
    queryKey: ['alerts', 'OPEN'],
    queryFn: () => unwrap(api.GET('/alerts', { params: { query: { status: 'OPEN' } } })),
    enabled: role === 'AUDITOR' || role === 'SUPERVISOR',
    refetchInterval: 15_000,
  })
  return { inbox: inbox.data?.items.filter((r) => r.can_decide).length ?? 0, alerts: alerts.data?.total ?? 0 }
}

/** The chain head, always in view: the product's whole promise in one line. */
function LedgerRail() {
  const q = useQuery({ queryKey: ['audit-head'], queryFn: () => unwrap(api.GET('/audit/head')), refetchInterval: 4000 })
  const prev = useRef<number | null>(null)
  const [bump, setBump] = useState(false)
  useEffect(() => {
    const seq = q.data?.head_seq
    if (seq == null) return
    if (prev.current != null && seq !== prev.current) { setBump(true); const t = setTimeout(() => setBump(false), 900); prev.current = seq; return () => clearTimeout(t) }
    prev.current = seq
  }, [q.data?.head_seq])
  const h = q.data
  return (
    <div className="border-b border-line bg-[#e9e3d6]">
      <div className="mx-auto flex h-8 max-w-[1320px] items-center gap-3 px-8 font-mono text-[11.5px] text-muted">
        <Lock className="size-3.5 text-stamp" />
        {h ? (
          <>
            <span>ledger</span>
            <span className={cn('rounded-[2px] px-1 text-ink transition-colors duration-700', bump && 'bg-[#e7dfc6]')}>entry #{h.head_seq}</span>
            <Tip content={<span className="break-all">{h.head_hash}</span>}><span className="cursor-default">{shortHash(h.head_hash, 10)}</span></Tip>
            <span className="text-faint">·</span>
            <span>{fmtRelative(h.at)}</span>
            <span className="ml-auto hidden sm:inline">sealed through #{h.sealed_upto}{h.checkpoint_id ? ` in checkpoint ${h.checkpoint_id}` : ''}{h.sealed_at ? `, ${fmtRelative(h.sealed_at)}` : ''}</span>
          </>
        ) : <span>reading ledger…</span>}
      </div>
    </div>
  )
}

export function Layout() {
  const { me, loading, signOut } = useAuth()
  const location = useLocation()
  const nav = useNavigate()
  const badges = useBadges(me?.role)
  const [q, setQ] = useState('')

  if (loading) return <div className="grid h-dvh place-items-center"><Spinner className="size-6" /></div>
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  const items = NAV.filter((i) => !i.roles || i.roles.includes(me.role))

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-surface focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-30">
        <div className="bg-navy-900 text-[#e9e3d4]">
          <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-8 px-8">
            <Link to="/" className="flex shrink-0 items-center gap-2.5">
              <Logo className="size-7" />
              <span className="serif text-[18px] leading-none font-semibold tracking-[-0.01em] text-[#f6f1e4]">Case-File Vault</span>
            </Link>
            <nav className="flex h-full items-stretch gap-6 overflow-x-auto">
              {items.map((i) => {
                const count = i.badge ? badges[i.badge] : 0
                return (
                  <NavLink key={i.to} to={i.to} end={i.to === '/'}
                    className={({ isActive }) => cn(
                      'relative flex items-center gap-1.5 border-b-2 pt-0.5 text-[13.5px] whitespace-nowrap transition-colors',
                      isActive ? 'border-[#e9c46a] font-medium text-white' : 'border-transparent text-[#e9e3d4]/70 hover:text-white')}>
                    {i.label}
                    {count > 0 && (
                      <span className={cn('min-w-[18px] rounded-[3px] px-1 text-center text-[11px] leading-[17px] font-semibold',
                        i.badge === 'alerts' ? 'bg-tape text-white' : 'bg-[#e9c46a] text-navy-950')}>{count}</span>
                    )}
                  </NavLink>
                )
              })}
            </nav>
            <div className="ml-auto flex items-center gap-4">
              {!['ADMIN', 'SUPER_ADMIN'].includes(me.role) && (
                <form className="relative hidden lg:block" onSubmit={(e) => { e.preventDefault(); if (q.trim()) nav(`/search?q=${encodeURIComponent(q.trim())}`) }}>
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-[#e9e3d4]/50" />
                  <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search files and text"
                    className="h-8 w-64 rounded-[4px] border border-white/10 bg-white/[0.06] pr-3 pl-8 text-[13px] text-white placeholder:text-[#e9e3d4]/45 focus:border-white/30 focus:bg-white/10 focus:outline-none" />
                </form>
              )}
              <DM.Root>
                <DM.Trigger className="flex items-center gap-2.5 rounded-[4px] py-1 pr-1 pl-1 hover:bg-white/5">
                  <Avatar name={me.full_name} tone="dark" />
                  <div className="hidden text-left leading-tight xl:block">
                    <div className="text-[13px] font-medium text-white">{me.full_name}</div>
                    <div className="text-[11.5px] text-[#e9e3d4]/60">{ROLE_LABEL[me.role]}</div>
                  </div>
                </DM.Trigger>
                <DM.Portal>
                  <DM.Content align="end" sideOffset={8} className="z-50 w-64 rounded-[6px] border border-line-strong bg-surface p-1 shadow-pop data-[state=open]:animate-pop-in">
                    <div className="px-3 py-2.5">
                      <div className="font-medium">{me.full_name}</div>
                      <div className="text-[12.5px] text-muted">{me.rank} · {me.unit_name}</div>
                      <div className="mt-1 font-mono text-[12px] text-ink-2">{me.service_id}</div>
                    </div>
                    <DM.Separator className="my-1 h-px bg-line" />
                    <DM.Item onSelect={() => nav('/settings')}
                      className="flex cursor-pointer items-center gap-2 rounded-[4px] px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-sunken">
                      <KeyRound className="size-4" />Settings — password, face, sessions
                    </DM.Item>
                    <DM.Item onSelect={() => window.open('/verify', '_blank')}
                      className="flex cursor-pointer items-center gap-2 rounded-[4px] px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-sunken">
                      <BookCheck className="size-4" />Public verification page
                    </DM.Item>
                    <DM.Item onSelect={async () => { await signOut(); nav('/login') }}
                      className="flex cursor-pointer items-center gap-2 rounded-[4px] px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-sunken">
                      <LogOut className="size-4" />Sign out
                    </DM.Item>
                  </DM.Content>
                </DM.Portal>
              </DM.Root>
            </div>
          </div>
        </div>
        <LedgerRail />
      </header>
      <main id="main" key={location.pathname} className="mx-auto w-full max-w-[1320px] flex-1 animate-fade-in px-8 pt-8 pb-16">
        <Outlet />
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1320px] flex-wrap justify-between gap-2 px-8 py-4 text-[12px] text-muted">
          <span>Case-File Vault · prototype for SIH 2026, PS 26190 · all names and records are fictional</span>
          <span>Times shown in IST</span>
        </div>
      </footer>
    </div>
  )
}
