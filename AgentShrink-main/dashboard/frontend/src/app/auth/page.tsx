'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { acceptPublicInvite, completePublicExternalAuth, consumePublicMagicLink, fetchPublicAuthProviders, fetchPublicSession, loginPublicSession, logoutPublicSession, requestPublicMagicLink, startPublicExternalAuth } from '@/lib/api'
import { PageShell, PageHeader, TerminalCard, TerminalInput, FieldLabel, PrimaryButton, SecondaryButton, Badge, ErrorBlock, SuccessBlock, LoadingTerminal, StatusDot } from '@/components/Terminal'

export default function AuthPage() {
  return (
    <Suspense fallback={<LoadingTerminal />}>
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
    <PageShell maxWidth={720}>
      <PageHeader
        title="SIGN IN"
        tag="session"
        description="Local session layer for the hosted product shape. Gives the product a real session contract for teams, projects, and project-scoped actions."
      />

      {error && <ErrorBlock message={error} />}
      {message && !error && <SuccessBlock message={message} />}

      <TerminalCard title="CREDENTIALS">
        <div style={{ display: 'grid', gap: 12 }}>
          <FieldLabel label="name">
            <TerminalInput value={userName} onChange={(e) => setUserName(e.target.value)} />
          </FieldLabel>
          <FieldLabel label="email">
            <TerminalInput value={userEmail} onChange={(e) => setUserEmail(e.target.value)} />
          </FieldLabel>
        </div>
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <StatusDot ok={!!session?.authenticated} />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            session: <code>{session?.authenticated ? 'authenticated' : 'signed-out'}</code>
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <PrimaryButton onClick={signIn}>CONTINUE</PrimaryButton>
          <SecondaryButton onClick={requestMagicLink}>EMAIL MAGIC LINK</SecondaryButton>
          {providerInfo?.auth?.provider === 'auth0' && (
            <SecondaryButton onClick={startExternalAuth}>AUTH0</SecondaryButton>
          )}
          <SecondaryButton onClick={signOut}>SIGN OUT</SecondaryButton>
          <Link href="/projects" style={{ color: '#6C63FF', textDecoration: 'none', padding: '6px 10px', fontSize: 13, fontWeight: 600 }}>
            Go to projects →
          </Link>
        </div>
        {deliveryPath && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10 }}>
            Delivered to: <code style={{ color: '#6C63FF' }}>{deliveryPath}</code>
          </div>
        )}
      </TerminalCard>

      <TerminalCard title="MAGIC-LINK SIGN IN">
        <FieldLabel label="token from local email outbox">
          <TerminalInput value={magicToken} onChange={(e) => setMagicToken(e.target.value)} placeholder="Paste magic-link token here" />
        </FieldLabel>
        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
          <PrimaryButton onClick={consumeMagicLink}>USE MAGIC LINK</PrimaryButton>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 10 }}>
          Emailed links open this page with <code style={{ color: 'var(--text-secondary)' }}>?magic_token=...</code> or <code style={{ color: 'var(--text-secondary)' }}>?invite_token=...</code>
        </div>
      </TerminalCard>
    </PageShell>
  )
}
