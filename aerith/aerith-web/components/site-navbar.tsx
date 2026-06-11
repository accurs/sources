'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { DOCS_URL, SUPPORT_URL } from '@/lib/aerith-data'

const links = [
  { href: '/commands', label: 'commands', external: false },
  { href: '/status', label: 'status', external: false },
  { href: DOCS_URL, label: 'docs', external: true },
]

export function SiteNavbar() {
  const pathname = usePathname()

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="fixed inset-x-0 top-4 z-50 flex justify-center px-4"
    >
      <nav className="flex items-center gap-1 rounded-full border border-border/70 bg-background/60 p-1.5 shadow-lg shadow-black/30 backdrop-blur-xl">
        {/* Logo */}
        <Link
          href="/"
          aria-label="aerith home"
          className="group flex size-9 items-center justify-center transition-transform duration-300 hover:scale-110"
        >
          <span className="relative block size-8 overflow-hidden rounded-full ring-1 ring-border transition-shadow duration-300 group-hover:ring-primary/60">
            <Image
              src="/aerith-avatar.png"
              alt="Aerith bot avatar"
              fill
              sizes="32px"
              className="object-cover"
            />
          </span>
        </Link>

        <span className="mx-0.5 h-5 w-px bg-border/70" aria-hidden="true" />

        {/* Links */}
        <div className="flex items-center">
          {links.map((link) => {
            const active = !link.external && pathname === link.href
            const content = (
              <span className="relative z-10">{link.label}</span>
            )
            const className = cn(
              'relative rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-200 sm:px-4',
              active
                ? 'text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )
            return link.external ? (
              <a
                key={link.href}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className={className}
              >
                {content}
              </a>
            ) : (
              <Link key={link.href} href={link.href} className={className}>
                {active && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 -z-0 rounded-full bg-primary"
                    transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                  />
                )}
                {content}
              </Link>
            )
          })}
        </div>

        <span className="mx-0.5 h-5 w-px bg-border/70" aria-hidden="true" />

        {/* Discord / support */}
        <a
          href={SUPPORT_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Join the support server on Discord"
          className="group flex size-9 items-center justify-center rounded-full transition-all duration-300 hover:scale-110 hover:bg-primary/15"
        >
          <Image
            src="/discord-white.png"
            alt="discord"
            width={18}
            height={18}
            className="size-[18px] opacity-70 transition-all duration-300 group-hover:scale-110 group-hover:opacity-100"
          />
        </a>
      </nav>
    </motion.header>
  )
}
