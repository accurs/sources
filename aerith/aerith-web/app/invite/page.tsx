import { redirect } from 'next/navigation'
import { INVITE_URL } from '@/lib/aerith-data'

export default function InvitePage() {
  redirect(INVITE_URL)
}
