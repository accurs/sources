import { redirect } from 'next/navigation'
import { SUPPORT_URL } from '@/lib/aerith-data'

export default function SupportPage() {
  redirect(SUPPORT_URL)
}
