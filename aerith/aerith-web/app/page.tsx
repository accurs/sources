import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SiteNavbar } from '@/components/site-navbar'
import { AerithWordmark } from '@/components/aerith-wordmark'

export default function HomePage() {
  return (
    <div className="flex h-[100svh] flex-col overflow-hidden">
      <SiteNavbar />

      <main className="flex flex-1 items-center justify-center px-4 sm:px-6">
        <section className="flex flex-col items-center text-center">
          <AerithWordmark />

          <p className="mt-5 max-w-md text-balance text-lg text-muted-foreground">
            made to ease community building
          </p>

          <div className="mt-9 flex flex-col items-center gap-3 sm:flex-row">
            <Button
              asChild
              size="lg"
              className="h-11 px-6 transition-transform duration-200 hover:scale-[1.03]"
            >
              <Link href="/invite">
                invite
                <span className="ml-2">→</span>
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-11 bg-transparent px-6 transition-colors duration-200 hover:border-primary/50"
            >
              <Link href="/support">support</Link>
            </Button>
          </div>
        </section>
      </main>
    </div>
  )
}
