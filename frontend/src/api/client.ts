import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

export type Schemas = components['schemas']

export class ApiProblem extends Error {
  status: number
  code: string
  detail?: string
  denyReason?: string
  errors?: { field: string; message: string }[]

  constructor(status: number, body: Partial<Schemas['Problem']> & { deny_reason?: string }) {
    super(body?.title ?? `Request failed (${status})`)
    this.status = status
    this.code = body?.code ?? 'ERROR'
    this.detail = body?.detail
    this.denyReason = body?.deny_reason
    this.errors = body?.errors
  }
}

const TOKEN_KEY = 'cfv.token'

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn
}

const auth: Middleware = {
  onRequest({ request }) {
    const t = tokenStore.get()
    if (t) request.headers.set('Authorization', `Bearer ${t}`)
    return request
  },
  onResponse({ response, request }) {
    if (response.status === 401 && !request.url.includes('/auth/')) onUnauthorized()
    return response
  },
}

export const api = createClient<paths>({ baseUrl: '/api/v1' })
api.use(auth)

/** Throw ApiProblem for error responses so TanStack Query sees a rejection. */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await p
  if (!response.ok) throw new ApiProblem(response.status, (error ?? {}) as never)
  return data as T
}

/** Multipart uploads (openapi-fetch's typed body doesn't model File well). */
export async function postForm<T>(url: string, form: FormData): Promise<T> {
  const t = tokenStore.get()
  const res = await fetch(`/api/v1${url}`, {
    method: 'POST',
    body: form,
    headers: t ? { Authorization: `Bearer ${t}` } : {},
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiProblem(res.status, body)
  return body as T
}
