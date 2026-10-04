const IST = 'Asia/Kolkata'

const dt = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit',
  minute: '2-digit', hour12: false,
})
const dOnly = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST, day: '2-digit', month: 'short', year: 'numeric',
})
const tOnly = new Intl.DateTimeFormat('en-IN', {
  timeZone: IST, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
})

export const fmtDateTime = (iso?: string | null) => (iso ? `${dt.format(new Date(iso))} IST` : '—')
export const fmtDate = (iso?: string | null) => (iso ? dOnly.format(new Date(iso)) : '—')
export const fmtTime = (iso?: string | null) => (iso ? tOnly.format(new Date(iso)) : '—')

export function fmtRelative(iso?: string | null): string {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 0) {
    const f = -s
    if (f < 3600) return `in ${Math.round(f / 60)} min`
    if (f < 86400) return `in ${Math.round(f / 3600)} h`
    return `in ${Math.round(f / 86400)} days`
  }
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} days ago`
  return fmtDate(iso)
}

export function fmtBytes(n?: number | null): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

export const shortHash = (h?: string | null, n = 6) => (h ? `${h.slice(0, n)}…${h.slice(-4)}` : '—')

export const humanize = (s?: string | null) =>
  s ? s.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()) : '—'

export const DOC_TYPE_LABEL: Record<string, string> = {
  FIR: 'FIR', COMPLAINT: 'Complaint', CASE_DIARY: 'Case diary', WITNESS_STATEMENT: 'Witness statement',
  VICTIM_STATEMENT: 'Victim statement', ACCUSED_STATEMENT: 'Accused statement',
  SEIZURE_MEMO: 'Seizure memo', ARREST_MEMO: 'Arrest memo', MEDICAL_REPORT: 'Medical report',
  FORENSIC_REPORT: 'Forensic report', PHOTO_EVIDENCE: 'Photo evidence', CCTV_STILL: 'CCTV still',
  INVESTIGATION_REPORT: 'Investigation report', CHARGESHEET: 'Charge-sheet',
  COURT_FILING: 'Court filing', COURT_ORDER: 'Court order', LEGAL_NOTICE: 'Legal notice',
  JUDGMENT: 'Judgment', OTHER: 'Other',
}

export const CASE_STATUS_LABEL: Record<string, string> = {
  REGISTERED: 'Registered', UNDER_INVESTIGATION: 'Under investigation',
  CHARGESHEET_FILED: 'Charge-sheet filed', FINAL_REPORT_FILED: 'Final report filed',
  UNDER_TRIAL: 'Under trial', DISPOSED: 'Disposed', CLOSED: 'Closed',
}

export const CATEGORY_LABEL: Record<string, string> = {
  CRIME_AGAINST_WOMEN: 'Crime against women', CRIME_AGAINST_CHILDREN: 'Crime against children',
  CYBER: 'Cyber crime', PROPERTY: 'Property', BODILY_HARM: 'Bodily harm', ECONOMIC: 'Economic',
  NARCOTICS: 'Narcotics', OTHER: 'Other',
}

export const ROLE_LABEL: Record<string, string> = {
  SUPER_ADMIN: 'Super Administrator',
  INVESTIGATOR: 'Investigating Officer', SUPERVISOR: 'Supervising Officer',
  PROSECUTOR: 'Public Prosecutor', FORENSIC_EXPERT: 'Forensic Expert', AUDITOR: 'Auditor',
  ADMIN: 'Administrator',
}

export const CAPACITY_LABEL: Record<string, string> = {
  LEAD_IO: 'Lead IO', CO_IO: 'Co-IO', SUPERVISOR: 'Supervisor', PROSECUTOR: 'Prosecutor',
  FORENSIC: 'Forensic',
}

export const DENY_TEXT: Record<string, string> = {
  NOT_A_CASE_MEMBER: 'You are not assigned to this case.',
  ACTION_NOT_PERMITTED: 'Your role on this case does not allow this.',
  ROLE_NOT_PERMITTED: 'Your role does not allow this.',
  SENSITIVITY: "This document's sensitivity level does not allow it.",
  CASE_CLOSED: 'The case is closed and read-only.',
  LEGAL_HOLD: 'The document is under legal hold.',
  SELF_APPROVAL: 'You cannot decide on your own request.',
}
