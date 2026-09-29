import { useEffect, useState } from 'react'
import { RouterProvider } from 'react-router-dom'
import { LoginPage } from '../pages/LoginPage'
import { onSessionChange, readSession, type Session } from '../lib/api/auth'
import { router } from './router'

export function App() {
  const [session, setSession] = useState<Session | null>(() => readSession())
  useEffect(() => onSessionChange(() => setSession(readSession())), [])
  if (!session) return <LoginPage onSuccess={setSession} />
  return <RouterProvider router={router} />
}
