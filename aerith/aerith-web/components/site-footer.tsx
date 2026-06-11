import Link from 'next/link'
import Image from 'next/image'
import { DOCS_URL, SUPPORT_URL } from '@/lib/aerith-data'

export function SiteFooter() {
  return (
    <footer className="border-t border-border/60">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="relative block size-8 overflow-hidden rounded-full ring-1 ring-border transition-shadow duration-300 group-hover:ring-primary/60">
            <Image
              src="/aerith-avatar.png"
              alt="Aerith bot avatar"
              fill
              sizes="32px"
              className="object-cover"
            />
          </span>
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} Aerith
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <Link
            href="/commands"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            commands
          </Link>
          <Link
            href="/status"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            status
          </Link>
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            documentation
          </a>
          <a
            href={SUPPORT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            support
          </a>
        </div>
      </div>
    </footer>
  )
}
