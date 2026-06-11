import type { Metadata } from 'next'
import { SiteNavbar } from '@/components/site-navbar'
import { SiteFooter } from '@/components/site-footer'
import { Reveal } from '@/components/reveal'
import { CommandsBrowser } from './commands-browser'

export const metadata: Metadata = {
  title: 'aerith',
  description: 'commands',
}

export default function CommandsPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteNavbar />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-16 pt-28 sm:px-6">
        <Reveal>
          <h1 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            commands
          </h1>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            every command aerith offers
          </p>
        </Reveal>

        <div className="mt-8">
          <CommandsBrowser />
        </div>
      </main>

      <SiteFooter />
    </div>
  )
}
