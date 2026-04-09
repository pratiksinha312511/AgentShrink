'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { acceptPublicInvite, completePublicExternalAuth, consumePublicMagicLink, fetchPublicAuthProviders, fetchPublicSession, loginPublicSession, logoutPublicSession, requestPublicMagicLink, startPublicExternalAuth } from '@/lib/api'

export default function AuthPage() {
  return (
    <Suspense fallback={<div className="card" style={{ padding: 24 }}>Loading auth...</div>}>
      <AuthPageInner />
    </Suspense>
  )
}

function AuthPageInner() {
  const searchParams = useSearchParams()
  const [session, setSession] = useState<any>(null)
  const [userName, setUserName] = useState('Local Owner')
  const [userEmail, setUserEmail] = useState('local-owner@agentshrink.local')
  const [magicToken, setMagicToken] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [deliveryPath, setDeliveryPath] = useState('')
  const [providerInfo, setProviderInfo] = useState<any>(null)

  useEffect(() => {
    Promise.all([fetchPublicSession(), fetchPublicAuthProviders()])
      .then(([data, providerData]) => {
        setSession(data)
        setProviderInfo(providerData)
        setUserName(data?.user?.name || 'Local Owner')
        setUserEmail(data?.user?.email || 'local-owner@agentshrink.local')
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const magicTokenFromUrl = searchParams.get('magic_token')
    const inviteTokenFromUrl = searchParams.get('invite_token')
    const authCode = searchParams.get('code')
    if (magicTokenFromUrl && magicTokenFromUrl !== magicToken) {
      setMagicToken(magicTokenFromUrl)
      consumePublicMagicLink({ token: magicTokenFromUrl })
        .then((data) => {
          setSession(data?.session || null)
          setMessage('Magic link accepted from the emailed URL.')
        })
        .catch((e: any) => setError(e.message || 'Failed to consume emailed magic link'))
      return
    }
    if (authCode) {
      completePublicExternalAuth({ code: authCode, redirect_uri: window.location.origin + '/auth' })
        .then((data) => {
          setSession(data?.session || null)
          setMessage('External auth completed successfully.')
        })
        .catch((e: any) => setError(e.message || 'Failed to complete external auth'))
      return
    }
    if (inviteTokenFromUrl && session?.authenticated) {
      acceptPublicInvite(inviteTokenFromUrl, { user_name: userName, user_email: userEmail })
        .then(() => setMessage('Invite accepted from the emailed URL.'))
        .catch((e: any) => setError(e.message || 'Failed to accept invite from URL'))
    }
  }, [searchParams, session?.authenticated])

  const signIn = async () => {
    try {
      setError('')
      const data = await loginPublicSession({ user_name: userName, user_email: userEmail })
      setSession(data)
      setMessage('Session ready. You can continue into projects.')
    } catch (e: any) {
      setError(e.message || 'Failed to create session')
    }
  }

  const signOut = async () => {
    try {
      setError('')
      const data = await logoutPublicSession()
      setSession(data)
      setMessage('Session cleared.')
    } catch (e: any) {
      setError(e.message || 'Failed to clear session')
    }
  }

  const requestMagicLink = async () => {
    try {
      setError('')
      const data = await requestPublicMagicLink({ user_email: userEmail, user_name: userName })
      setDeliveryPath(data?.delivery_path || '')
      setMessage(`Magic link created for ${userEmail}. Check the local email outbox file and paste the token below.`)
    } catch (e: any) {
      setError(e.message || 'Failed to request magic link')
    }
  }

  const consumeMagicLink = async () => {
    try {
      setError('')
      const data = await consumePublicMagicLink({ token: magicToken })
      setSession(data?.session || null)
      setUserName(data?.session?.user?.name || userName)
      setUserEmail(data?.session?.user?.email || userEmail)
      setMessage('Magic link accepted. Session is now authenticated.')
      setMagicToken('')
    } catch (e: any) {
      setError(e.message || 'Failed to consume magic link')
    }
  }

  const startExternalAuth = async () => {
    try {
      setError('')
      const data = await startPublicExternalAuth({ redirect_uri: window.location.origin + '/auth' })
      if (data?.authorize_url) {
        window.location.href = data.authorize_url
        return
      }
      setMessage('External auth provider did not return an authorize URL.')
    } catch (e: any) {
      setError(e.message || 'Failed to start external auth')
    }
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Hosted-style auth/session</div>
        <h1 style={{ fontSize: 24, margin: '0 0 8px', color: 'var(--text-primary)' }}>Sign in</h1>
        <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          This is the first local session layer for the hosted product shape. It is not full auth yet, but it gives the product
          a real session contract for teams, projects, and project-scoped actions.
        </p>
      </div>

      {(error || message) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, color: error ? '#A32D2D' : '#27500A' }}>
          {error || message}
        </div>
      )}

      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: 'grid', gap: 12 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Name</span>
            <input value={userName} onChange={(e) => setUserName(e.target.value)} style={inputStyle} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Email</span>
            <input value={userEmail} onChange={(e) => setUserEmail(e.target.value)} style={inputStyle} />
          </label>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 12 }}>
          Current session: <code>{session?.authenticated ? 'authenticated' : 'signed-out'}</code>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <button onClick={signIn} style={buttonStyle}>Continue</button>
          <button onClick={requestMagicLink} style={buttonStyle}>Email magic link</button>
          {providerInfo?.auth?.provider === 'auth0' && (
            <button onClick={startExternalAuth} style={buttonStyle}>Continue with Auth0</button>
          )}
          <button onClick={signOut} style={buttonStyle}>Sign out</button>
          <Link href="/projects" style={linkStyle}>Go to projects</Link>
        </div>
        {deliveryPath && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10 }}>
            Delivered locally to: <code>{deliveryPath}</code>
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Magic-link sign in</div>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Token from local email outbox</span>
          <input value={magicToken} onChange={(e) => setMagicToken(e.target.value)} style={inputStyle} placeholder="Paste magic-link token here" />
        </label>
        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <button onClick={consumeMagicLink} style={buttonStyle}>Use magic link</button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10 }}>
          Emailed links can open this page directly with <code>?magic_token=...</code> or <code>?invite_token=...</code>.
        </div>
      </div>
    </div>
  )
}

const inputStyle = {
  width: '100%',
  borderRadius: 10,
  border: '0.5px solid var(--border)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  padding: '10px 12px',
  fontSize: 13,
} as const

const buttonStyle = {
  border: '0.5px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontWeight: 600,
  padding: '8px 10px',
  cursor: 'pointer',
} as const

const linkStyle = {
  textDecoration: 'none',
  color: '#185FA5',
  fontWeight: 600,
  padding: '8px 10px',
} as const
