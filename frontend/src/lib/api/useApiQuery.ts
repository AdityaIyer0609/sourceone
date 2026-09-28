import { useCallback, useEffect, useRef, useState } from 'react'

interface QueryState<T> {
  requestKey: string | null
  key: string | null
  data?: T
  error?: unknown
  updatedAt?: Date
}

/**
 * Fetches when `key` changes (pass null to skip). Data for the same key is kept while a
 * reload is in flight so screens do not flash back to their loading state.
 */
export function useApiQuery<T>(key: string | null, fetcher: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<QueryState<T>>({ requestKey: null, key: null })
  const [nonce, setNonce] = useState(0)
  const fetcherRef = useRef(fetcher)
  const requestKey = key === null ? null : `${key}#${nonce}`

  useEffect(() => {
    fetcherRef.current = fetcher
  })

  useEffect(() => {
    if (requestKey === null) return
    const controller = new AbortController()
    fetcherRef.current(controller.signal).then(
      (data) => setState({ requestKey, key, data, updatedAt: new Date() }),
      (error: unknown) => {
        if (controller.signal.aborted) return
        setState((previous) => (previous.key === key ? { ...previous, requestKey, error } : { requestKey, key, error }))
      },
    )
    return () => controller.abort()
  }, [requestKey, key])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  const settled = state.requestKey === requestKey
  const sameKey = state.key === key

  return {
    data: sameKey ? state.data : undefined,
    error: settled ? state.error : undefined,
    isLoading: requestKey !== null && !settled,
    updatedAt: sameKey ? state.updatedAt : undefined,
    reload,
  }
}
