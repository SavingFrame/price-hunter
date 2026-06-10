import { Link } from "@tanstack/react-router"
import {
  BadgeEuro,
  PackageSearch,
  ReceiptText,
  ShoppingBasket,
} from "lucide-react"

import { Appearance } from "@/components/Common/Appearance"

interface AuthLayoutProps {
  children: React.ReactNode
}

const featureItems = [
  {
    icon: PackageSearch,
    title: "Search products",
    description: "Browse normalized Croatian grocery products.",
  },
  {
    icon: BadgeEuro,
    title: "Track price moves",
    description: "Spot drops and increases across retailers.",
  },
  {
    icon: ReceiptText,
    title: "Prepare baskets",
    description: "Connect shopping history with current prices.",
  },
]

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="relative min-h-svh overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.18),transparent_34rem),radial-gradient(circle_at_top_right,rgba(132,204,22,0.12),transparent_30rem)]" />

      <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
            <ShoppingBasket className="size-5" />
          </span>
          <div>
            <p className="font-semibold tracking-tight">Cjenolovac</p>
            <p className="text-xs text-muted-foreground">
              Croatian grocery intelligence
            </p>
          </div>
        </Link>
        <Appearance />
      </header>

      <main className="mx-auto grid min-h-[calc(100svh-4rem)] max-w-7xl items-center gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <section className="hidden lg:block">
          <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-card/80 p-8 shadow-2xl shadow-primary/5">
            <div className="absolute right-0 top-0 h-64 w-64 rounded-full bg-primary/15 blur-3xl" />
            <div className="relative space-y-8">
              <div className="space-y-4">
                <div className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-sm text-muted-foreground">
                  <BadgeEuro className="size-4 text-primary" />
                  Live price radar
                </div>
                <h1 className="max-w-xl text-5xl font-semibold tracking-tight">
                  Find what got cheaper before you shop.
                </h1>
                <p className="max-w-lg text-base leading-7 text-muted-foreground">
                  Sign in to save your account settings, manage receipt flows,
                  and keep your grocery intelligence ready across sessions.
                </p>
              </div>

              <div className="grid gap-3">
                {featureItems.map(({ icon: Icon, title, description }) => (
                  <div
                    className="rounded-2xl border bg-background/60 p-4"
                    key={title}
                  >
                    <Icon className="mb-3 size-5 text-primary" />
                    <p className="font-medium">{title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {description}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="flex justify-center lg:justify-end">
          <div className="w-full max-w-md">{children}</div>
        </section>
      </main>
    </div>
  )
}
