'use client'

import useSWR from 'swr'
import { motion, AnimatePresence } from 'motion/react'
import { STATUS_URL, fetcher, parseStatus, fallbackStatus } from '@/lib/aerith-data'
import { cn } from '@/lib/utils'

function toNum(v: string) {
  const n = parseInt(v.replace(/[^0-9]/g, ''), 10)
  return Number.isNaN(n) ? 0 : n
}

function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted/60', className)} />
}

function LoadingSkeleton() {
  return (
    <motion.div
      key="loading"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
          </span>
          <Skeleton className="h-4 w-40" />
        </div>
        <Skeleton className="h-9 w-24" />
        <Skeleton className="h-4 w-52" />
      </div>

      {/* Summary cards skeleton */}
      <div className="mt-8 grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08, duration: 0.35 }}
            className="rounded-2xl border border-border/50 bg-card/40 p-5"
          >
            <Skeleton className="h-3 w-28" />
            <Skeleton className="mt-2 h-8 w-20" />
          </motion.div>
        ))}
      </div>

      <Skeleton className="mt-10 h-6 w-16" />
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {[0, 1, 2, 3].map((i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07, duration: 0.35 }}
            className="rounded-2xl border border-border/50 bg-card/40 p-5"
          >
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-6 w-16 rounded-full" />
            </div>
            <div className="mt-4 grid grid-cols-3 gap-4">
              {[0, 1, 2].map((j) => (
                <div key={j}>
                  <Skeleton className="h-3 w-12" />
                  <Skeleton className="mt-1.5 h-4 w-16" />
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
        <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
        <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
        <span className="ml-1">fetching status…</span>
      </div>
    </motion.div>
  )
}

export function StatusBoard() {
  const { data, error, isLoading } = useSWR(STATUS_URL, fetcher, {
    fallbackData: fallbackStatus,
    refreshInterval: 30_000,
    revalidateOnFocus: false,
  })

  const shards = parseStatus(error ? fallbackStatus : data)

  const totalGuilds = shards.reduce((s, sh) => s + toNum(sh.guilds), 0)
  const totalUsers = shards.reduce((s, sh) => s + toNum(sh.users), 0)
  const avgLatency = shards.length
    ? Math.round(shards.reduce((s, sh) => s + toNum(sh.latency), 0) / shards.length)
    : 0

  return (
    <AnimatePresence mode="wait">
      {isLoading ? (
        <LoadingSkeleton key="skeleton" />
      ) : (
        <motion.div
          key="content"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35 }}
        >
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="flex flex-col gap-2"
          >
            <div className="flex items-center gap-2.5">
              <span className="relative flex size-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
              </span>
              <span className="text-sm font-medium text-primary">all systems operational</span>
            </div>
            <h1 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              status
            </h1>
            <p className="max-w-lg text-sm text-muted-foreground">real-time health of aerith</p>
          </motion.div>

          {/* Summary */}
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {[
              { label: 'average latency', value: `${avgLatency}ms` },
              { label: 'guilds', value: totalGuilds.toLocaleString() },
              { label: 'users', value: totalUsers.toLocaleString() },
            ].map((card, i) => (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay: i * 0.08 }}
                className="rounded-2xl border border-border/70 bg-card/50 p-5"
              >
                <p className="text-xs text-muted-foreground">{card.label}</p>
                <p className="mt-1 text-2xl font-semibold tracking-tight">{card.value}</p>
              </motion.div>
            ))}
          </div>

          {/* Shards */}
          <h2 className="mt-10 text-lg font-semibold tracking-tight">Shards</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {shards.map((shard, i) => (
              <motion.div
                key={shard.name}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{
                  duration: 0.45,
                  ease: [0.16, 1, 0.3, 1],
                  delay: Math.min(i * 0.05, 0.25),
                }}
                className="rounded-2xl border border-border/70 bg-card/50 p-5 transition-colors duration-300 hover:border-primary/40"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold capitalize tracking-tight">
                    {shard.name.replace(/_/g, ' ')}
                  </h3>
                  <span className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                    <span className="size-1.5 rounded-full bg-primary" />
                    Online
                  </span>
                </div>

                <dl className="mt-4 grid grid-cols-3 gap-4">
                  <Metric label="latency" value={shard.latency} />
                  <Metric label="guilds" value={toNum(shard.guilds).toLocaleString()} />
                  <Metric label="users" value={toNum(shard.users).toLocaleString()} />
                </dl>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-mono text-sm font-semibold">{value}</dd>
    </div>
  )
}