// Local demo identity only. The backend accepts the X-Demo-User header solely when its
// DEMO_AUTH_ENABLED setting is on. Every entry point checks import.meta.env.DEV so this module
// is dead code in production builds. This is not an authentication mechanism.

const DEMO_USERS = {
  asha: { email: 'asha@sourceone.demo', name: 'Asha Mehta', role: 'Platform admin', initials: 'AM' },
  ravi: { email: 'ravi@sourceone.demo', name: 'Ravi Iyer', role: 'Pricing admin', initials: 'RI' },
  meera: { email: 'meera@sourceone.demo', name: 'Meera Shah', role: 'Pricing admin', initials: 'MS' },
  buyer: { email: 'buyer@ardent.demo', name: 'Arjun Patel', role: 'Buyer · Ardent', initials: 'AP' },
  supplier: { email: 'supplier@zenith.demo', name: 'Zoya Khan', role: 'Supplier · Zenith', initials: 'ZK' },
} as const

export type DemoUserKey = keyof typeof DEMO_USERS

const STORAGE_KEY = 'sourceone.demoUser'
const QUERY_PARAM = 'demoUser'

function isDemoUserKey(value: string | null | undefined): value is DemoUserKey {
  return !!value && value in DEMO_USERS
}

function initialUser(): DemoUserKey | null {
  if (!import.meta.env.DEV || import.meta.env.VITE_DEMO_AUTH !== 'true') return null
  const fromQuery = new URLSearchParams(window.location.search).get(QUERY_PARAM)
  if (isDemoUserKey(fromQuery)) {
    window.localStorage.setItem(STORAGE_KEY, fromQuery)
    return fromQuery
  }
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (isDemoUserKey(stored)) return stored
  const fallback = import.meta.env.VITE_DEMO_USER
  return isDemoUserKey(fallback) ? fallback : 'buyer'
}

const currentUser = initialUser()

export function getDemoUser() {
  if (!import.meta.env.DEV || !currentUser) return null
  return { key: currentUser, ...DEMO_USERS[currentUser] }
}

/** Switches the demo identity and reloads so every screen refetches as that user. */
export function switchDemoUser(key: DemoUserKey) {
  if (!import.meta.env.DEV || !currentUser) throw new Error('Demo auth is disabled')
  window.localStorage.setItem(STORAGE_KEY, key)
  window.location.reload()
}

export function demoAuthHeaders(): Record<string, string> {
  if (!import.meta.env.DEV || !currentUser) return {}
  return { 'X-Demo-User': DEMO_USERS[currentUser].email }
}

if (import.meta.env.DEV && currentUser) {
  // Console helper for local demos: sourceoneDemo.use('ravi')
  Object.assign(window, { sourceoneDemo: { users: Object.keys(DEMO_USERS), current: currentUser, use: switchDemoUser } })
}
