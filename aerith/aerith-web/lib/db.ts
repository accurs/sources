import { Pool } from 'pg'

export const db = new Pool({
  user: 'aerith',
  password: 'wowow',
  host: '127.0.0.1',
  port: 5432,
  database: 'aerith',
})