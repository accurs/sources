import 'react/jsx-runtime'
import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const geist = Geist({ subsets: ['latin'], variable: '--font-geist' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' })

export const metadata: Metadata = {
  title: 'aerith',
  description: 'aerith',
}

export const viewport = {
  themeColor: '#0b0d12',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const isProduction = (globalThis as any).process?.env?.NODE_ENV === 'production'

  return (
    <html lang="en" className={`dark bg-background ${geist.variable} ${geistMono.variable}`}>
      <body className="font-sans antialiased">
        {children}
        {isProduction && <Analytics />}
      </body>
    </html>
  )
}
