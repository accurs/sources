'use client'

import { useState } from 'react'

export function AerithWordmark() {
  const [hovered, setHovered] = useState(false)

  return (
    <h1
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="group relative cursor-default select-none text-7xl font-semibold tracking-tighter sm:text-8xl"
    >
      {/* Base / glow layer */}
      <span
        aria-hidden="true"
        className={`absolute inset-0 bg-gradient-to-b from-primary to-primary/40 bg-clip-text text-transparent blur-xl transition-opacity duration-500 ${
          hovered ? 'opacity-60' : 'opacity-0'
        }`}
      >
        aerith
      </span>

      {/* Animated shine layer */}
      <span
        className="relative bg-[length:200%_100%] bg-clip-text text-transparent transition-[background-position] duration-700 ease-out"
        style={{
          backgroundImage:
            'linear-gradient(110deg, var(--foreground) 0%, var(--foreground) 35%, var(--primary) 50%, var(--foreground) 65%, var(--foreground) 100%)',
          backgroundPosition: hovered ? '-100% 0' : '100% 0',
        }}
      >
        aerith
      </span>
    </h1>
  )
}
