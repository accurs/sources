import type { Metadata } from 'next'
import { SiteNavbar } from '@/components/site-navbar'
import { SiteFooter } from '@/components/site-footer'
import { StatusBoard } from './status-board'

export const metadata: Metadata = {
  title: 'aerith',
  description: 'status',
}

export default function StatusPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteNavbar />

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-16 pt-28 sm:px-6">
        <StatusBoard />
      </main>

      <SiteFooter />
    </div>
  )
}