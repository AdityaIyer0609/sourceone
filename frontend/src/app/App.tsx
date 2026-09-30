import { useEffect, useState } from 'react'
import { RouterProvider } from 'react-router-dom'
import { BrandIntro } from '../components/brand/BrandIntro'
import { LoginPage } from '../pages/LoginPage'
import { onSessionChange, readSession, type Session } from '../lib/api/auth'
import { router } from './router'

export function App() {
  const [session, setSession] = useState<Session | null>(() => readSession())
  const [phase, setPhase] = useState<'login' | 'enter' | 'ready'>(() => (readSession() ? 'ready' : 'login'))
  const [reveal, setReveal] = useState(false)
  const [holdLogin, setHoldLogin] = useState(false)

  useEffect(() => onSessionChange(() => {
    const next = readSession()
    setSession(next)
    if (!next) {
      setPhase('login')
      setReveal(false)
      setHoldLogin(false)
    }
  }), [])

  useEffect(() => {
    if (!holdLogin) return
    const wait = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 260
    const timer = window.setTimeout(() => setHoldLogin(false), wait)
    return () => window.clearTimeout(timer)
  }, [holdLogin])

  const begin = (next: Session) => {
    setSession(next)
    setReveal(false)
    setPhase('enter')
    setHoldLogin(true)
  }

  return (
    <>
      {session && (
        <div className={phase === 'enter' ? `app-enter${reveal ? ' is-revealing' : ''}` : undefined} inert={phase === 'enter' ? true : undefined}>
          <RouterProvider router={router} />
        </div>
      )}
      {(phase === 'login' || holdLogin) && (
        <div className={phase === 'enter' ? 'login-leave' : undefined}>
          <LoginPage onSuccess={begin} />
        </div>
      )}
      {phase === 'enter' && <BrandIntro onReveal={() => setReveal(true)} onDone={() => { setPhase('ready'); setReveal(false) }} />}
    </>
  )
}
