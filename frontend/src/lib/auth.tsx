import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore, unwrap, type Schemas } from '@/api/client'

type Me = Schemas['Me']

const AuthCtx = createContext<{
  me: Me | null
  loading: boolean
  signIn: (token: string, me: Me) => void
  signOut: () => Promise<void>
}>({ me: null, loading: true, signIn: () => {}, signOut: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const hasToken = !!tokenStore.get()
  const { data, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => unwrap(api.GET('/auth/me')),
    enabled: hasToken,
    retry: false,
    staleTime: 60_000,
  })

  const clear = useCallback(() => {
    tokenStore.clear()
    qc.clear()
    if (!location.pathname.startsWith('/login') && !location.pathname.startsWith('/verify')) {
      location.assign('/login')
    }
  }, [qc])

  useEffect(() => setUnauthorizedHandler(clear), [clear])

  const signIn = (token: string, me: Me) => {
    tokenStore.set(token)
    qc.setQueryData(['me'], me)
  }
  const signOut = async () => {
    await api.POST('/auth/logout').catch(() => {})
    tokenStore.clear()
    qc.clear()
  }

  return (
    <AuthCtx.Provider value={{ me: hasToken ? (data ?? null) : null, loading: hasToken && isLoading, signIn, signOut }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
