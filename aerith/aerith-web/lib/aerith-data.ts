export const INVITE_URL =
  'https://discord.com/oauth2/authorize?client_id=1488218644625494289&scope=bot+applications.commands&permissions=8'
export const SUPPORT_URL = 'https://discord.gg/aerithbot'
export const DOCS_URL = 'https://docs.aerith.lol'

export const API_BASE = 'https://api.aerith.lol/get'
export const COMMANDS_URL = `${API_BASE}/commands`
export const STATUS_URL = `${API_BASE}/status`

export const fetcher = async (url: string) => {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Request failed: ${res.status}`)
  return res.json()
}

/* ---------- Commands ----------
 * API shape (commands.json):
 * {
 *   "extension": {
 *     "command": { "aliases": ["a","b"], "permissions": ["a_permission"] }
 *   }
 * }
 */
export type CommandEntry = {
  name: string
  aliases: string[]
  permissions: string[]
}

export type Extension = {
  name: string
  commands: CommandEntry[]
}

export function parseCommands(data: unknown): Extension[] {
  if (!data || typeof data !== 'object') return []
  return Object.entries(data as Record<string, unknown>).map(([extName, cmds]) => {
    const commands: CommandEntry[] =
      cmds && typeof cmds === 'object'
        ? Object.entries(cmds as Record<string, any>).map(([cmdName, info]) => ({
            name: cmdName,
            aliases: Array.isArray(info?.aliases) ? info.aliases : [],
            permissions: Array.isArray(info?.permissions) ? info.permissions : [],
          }))
        : []
    return { name: extName, commands }
  })
}

/* ---------- Status ----------
 * API shape (status.json):
 * { "shard_1": { "latency": "19ms", "users": "900", "guilds": "6772727" } }
 */
export type ShardEntry = {
  name: string
  latency: string
  users: string
  guilds: string
}

export function parseStatus(data: unknown): ShardEntry[] {
  if (!data || typeof data !== 'object') return []
  return Object.entries(data as Record<string, any>).map(([name, info]) => ({
    name,
    latency: String(info?.latency ?? '—'),
    users: String(info?.users ?? '0'),
    guilds: String(info?.guilds ?? '0'),
  }))
}

/* ---------- Fallback data (used when the API is unreachable) ---------- */
export const fallbackCommands = {
  Moderation: {
    ban: { aliases: ['b', 'hammer'], permissions: ['Ban Members'] },
    kick: { aliases: ['k'], permissions: ['Kick Members'] },
    mute: { aliases: ['timeout', 'silence'], permissions: ['Moderate Members'] },
    warn: { aliases: ['w'], permissions: ['Manage Messages'] },
    purge: { aliases: ['clear', 'clean'], permissions: ['Manage Messages'] },
  },
  Fun: {
    '8ball': { aliases: ['8b'], permissions: [] },
    meme: { aliases: ['memes'], permissions: [] },
    trivia: { aliases: ['quiz'], permissions: [] },
    rps: { aliases: ['rockpaperscissors'], permissions: [] },
  },
  Utility: {
    userinfo: { aliases: ['whois', 'ui'], permissions: [] },
    serverinfo: { aliases: ['si', 'guild'], permissions: [] },
    avatar: { aliases: ['av', 'pfp'], permissions: [] },
    poll: { aliases: ['vote'], permissions: ['Manage Messages'] },
  },
  Leveling: {
    rank: { aliases: ['level', 'xp'], permissions: [] },
    leaderboard: { aliases: ['lb', 'top'], permissions: [] },
    setxp: { aliases: ['givexp'], permissions: ['Manage Server'] },
  },
}

export const fallbackStatus = {
  shard_0: { latency: '15ms', users: '48210', guilds: '1204' },
  shard_1: { latency: '18ms', users: '51980', guilds: '1322' },
  shard_2: { latency: '12ms', users: '46150', guilds: '1188' },
  shard_3: { latency: '21ms', users: '50320', guilds: '1290' },
}
