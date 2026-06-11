'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { motion, AnimatePresence } from 'motion/react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  COMMANDS_URL,
  fetcher,
  parseCommands,
  fallbackCommands,
  type CommandEntry,
} from '@/lib/aerith-data'

function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-muted/60',
        className,
      )}
    />
  )
}

function CommandCardSkeleton() {
  return (
    <div className="rounded-2xl border border-border/50 bg-card/40 p-5">
      <Skeleton className="h-7 w-28" />
      <div className="mt-4 space-y-2.5 border-t border-border pt-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-3 w-14" />
          <Skeleton className="h-5 w-24" />
        </div>
        <div className="flex items-center justify-between">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-5 w-16" />
        </div>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <motion.div
      key="loading"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-10"
    >
      {[0, 1].map((sectionIdx) => (
        <div key={sectionIdx}>
          <div className="flex items-center gap-3">
            <Skeleton className="h-6 w-32" />
            <span className="text-xs text-muted-foreground/60 animate-pulse">
              loading…
            </span>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: (sectionIdx * 4 + i) * 0.05, duration: 0.35 }}
              >
                <CommandCardSkeleton />
              </motion.div>
            ))}
          </div>
        </div>
      ))}
    </motion.div>
  )
}

export function CommandsBrowser() {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState('all')

  const { data, error, isLoading } = useSWR(COMMANDS_URL, fetcher, {
    fallbackData: fallbackCommands,
    revalidateOnFocus: false,
  })

  const extensions = parseCommands(error ? fallbackCommands : data)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    return extensions
      .filter((ext) => active === 'all' || ext.name === active)
      .map((ext) => ({
        ...ext,
        commands: ext.commands.filter((c) => {
          if (!q) return true
          return (
            c.name.toLowerCase().includes(q) ||
            c.aliases.some((a) => a.toLowerCase().includes(q))
          )
        }),
      }))
      .filter((ext) => ext.commands.length > 0)
  }, [extensions, active, query])

  const total = results.reduce((s, e) => s + e.commands.length, 0)

  return (
    <div>
      <div className="relative">
        <Search className="absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search commands..."
          className="h-11 rounded-full border-border/70 bg-card/50 pl-11"
          aria-label="Search commands"
        />
      </div>

      {/* Extension filter pills */}
      <div className="mt-4 flex flex-wrap gap-2">
        <FilterPill label="All" value="all" active={active} onSelect={setActive} />
        {extensions.map((ext) => (
          <FilterPill
            key={ext.name}
            label={ext.name}
            value={ext.name}
            active={active}
            onSelect={setActive}
          />
        ))}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        {isLoading ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
            <span className="ml-1">loading commands…</span>
          </span>
        ) : (
          `${total} command${total === 1 ? '' : 's'}`
        )}
      </p>
      <div className="mt-6">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <LoadingSkeleton key="skeleton" />
          ) : (
            <motion.div
              key="content"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col gap-10"
            >
              <AnimatePresence mode="popLayout">
                {results.map((ext) => (
                  <motion.section
                    key={ext.name}
                    layout
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <h2 className="text-lg font-semibold tracking-tight">{ext.name}</h2>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {ext.commands.map((command, i) => (
                        <CommandCard key={command.name} command={command} index={i} />
                      ))}
                    </div>
                  </motion.section>
                ))}
              </AnimatePresence>

              {results.length === 0 && (
                <div className="rounded-2xl border border-dashed border-border bg-card/40 p-12 text-center">
                  <p className="font-medium">no commands found</p>
                  <p className="mt-1 text-sm text-muted-foreground">try a different search term.</p>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function FilterPill({
  label,
  value,
  active,
  onSelect,
}: {
  label: string
  value: string
  active: string
  onSelect: (v: string) => void
}) {
  const isActive = active === value
  return (
    <button
      onClick={() => onSelect(value)}
      className={cn(
        'relative rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors duration-200',
        isActive ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {isActive && (
        <motion.span
          layoutId="ext-pill"
          className="absolute inset-0 -z-0 rounded-full bg-primary"
          transition={{ type: 'spring', stiffness: 400, damping: 32 }}
        />
      )}
      <span className="relative z-10">{label}</span>
    </button>
  )
}

function CommandCard({ command, index }: { command: CommandEntry; index: number }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: Math.min(index * 0.04, 0.2) }}
      className="group rounded-2xl border border-border/70 bg-card/50 p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40"
    >
      <span className="inline-block rounded-md bg-primary/10 px-2 py-1 font-mono text-sm font-semibold text-primary">
        ,{command.name}
      </span>

      <dl className="mt-4 space-y-2.5 border-t border-border pt-4 text-sm">
        <Row label="Aliases">
          {command.aliases.length ? (
            <span className="flex flex-wrap justify-end gap-1.5">
              {command.aliases.map((a) => (
                <span
                  key={a}
                  className="rounded border border-border bg-secondary px-1.5 py-0.5 font-mono text-xs"
                >
                  {a}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-muted-foreground">None</span>
          )}
        </Row>
        <Row label="Permissions">
          {command.permissions.length ? (
            <span className="flex flex-wrap justify-end gap-1.5">
              {command.permissions.map((p) => (
                <span
                  key={p}
                  className="rounded border border-border bg-secondary px-1.5 py-0.5 text-xs"
                >
                  {p}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-muted-foreground">none</span>
          )}
        </Row>
      </dl>
    </motion.div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}