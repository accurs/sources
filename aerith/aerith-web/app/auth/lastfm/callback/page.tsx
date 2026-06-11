import type { Metadata } from 'next'
import { SiteNavbar } from '@/components/site-navbar'
import { SiteFooter } from '@/components/site-footer'
import { Reveal } from '@/components/reveal'
import { CheckCircle, XCircle } from 'lucide-react'
import { db } from '@/lib/db'

export async function consumeSessionKey(sessionKey: string, discordId: string) {
  const result = await db.query(
    `
    UPDATE lastfm
    SET sessionused = TRUE
    WHERE session_key = $1
      AND sessionused = FALSE
    RETURNING discord_id, lastfm_username
    `,
    [sessionKey]
  )

  if (result.rowCount === 0) return null

  return result.rows[0]
}

export const metadata: Metadata = {
  title: 'aerith',
  description: 'callback (do not open this page directly)',
}

const SESSION_KEY_PARAM = 'a-18a0fbb9-1c83-4c8e-9baf-5c8c580d0a7e'

type Props = {
  searchParams: {
    success?: string
    user?: string
    [SESSION_KEY_PARAM]?: string
  }
}

export default async function CallbackPage({ searchParams }: Props) {
  const success = searchParams.success === 'true'
  const user = searchParams.user
  const sessionKey = searchParams[SESSION_KEY_PARAM]

  const valid = success && user && sessionKey

  let dbResult = null

  if (valid && sessionKey && user) {
    dbResult = await consumeSessionKey(sessionKey, user)
  }

  const ok = Boolean(dbResult)

  return (
    <div className="flex min-h-screen flex-col">
      <SiteNavbar />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-16 pt-28 sm:px-6">
        <Reveal>
          <div className="flex items-center gap-3">
            {ok ? (
              <CheckCircle className="h-6 w-6 text-green-500" />
            ) : (
              <XCircle className="h-6 w-6 text-red-500" />
            )}

            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              {ok ? 'connected' : 'failed callback'}
            </h1>
          </div>

          <p className="mt-2 text-sm text-muted-foreground">
            {ok
              ? `lastfm linked for ${dbResult.lastfm_username}`
              : 'invalid request or session already used'}
          </p>
        </Reveal>
      </main>

      <SiteFooter />
    </div>
  )
}