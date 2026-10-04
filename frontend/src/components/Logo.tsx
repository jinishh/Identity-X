/** A tied case file seen edge-on: the folder, its red tape, and a seal. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect x="3" y="6" width="26" height="20" rx="2" fill="#d8c59b" />
      <path d="M3 10h26" stroke="#b9a473" strokeWidth="1" />
      <rect x="3" y="14.5" width="26" height="3" fill="#a8352b" />
      <circle cx="22" cy="16" r="4.2" fill="#4c3c86" />
      <path d="M20.2 16l1.3 1.3 2.4-2.6" fill="none" stroke="#f1ede4" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
