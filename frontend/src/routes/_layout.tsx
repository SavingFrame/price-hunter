import { createFileRoute, Link, Outlet } from "@tanstack/react-router"
import {
  ListChecks,
  LogIn,
  LogOut,
  PackageSearch,
  ReceiptText,
  Settings,
  ShoppingBasket,
  UserPlus,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout")({
  component: Layout,
})

function Layout() {
  const { logout, user } = useAuth()
  const loggedIn = isLoggedIn()

  return (
    <div className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.18),transparent_34rem),radial-gradient(circle_at_top_right,rgba(132,204,22,0.12),transparent_30rem)]" />
      <header className="sticky top-0 z-20 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex min-w-0 items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
              <ShoppingBasket className="size-5" />
            </span>
            <div className="min-w-0 leading-tight">
              <p className="truncate font-semibold tracking-tight">
                Cjenolovac
              </p>
              <p className="hidden truncate text-xs text-muted-foreground xl:block">
                Croatian grocery intelligence
              </p>
            </div>
          </Link>

          <nav className="hidden flex-1 items-center justify-center md:flex">
            <div className="flex items-center gap-1 rounded-full border border-border/70 bg-muted/30 p-1 text-sm text-muted-foreground">
              <Link
                className="flex items-center gap-2 rounded-full px-3 py-1.5 transition hover:bg-background/70 hover:text-foreground"
                activeProps={{
                  className: "bg-background text-foreground shadow-sm",
                }}
                to="/products"
              >
                <PackageSearch className="size-4" />
                Products
              </Link>
              <Link
                className="flex items-center gap-2 rounded-full px-3 py-1.5 transition hover:bg-background/70 hover:text-foreground"
                activeProps={{
                  className: "bg-background text-foreground shadow-sm",
                }}
                to="/product-lists"
              >
                <ListChecks className="size-4" />
                Lists
              </Link>
              <Link
                className="flex items-center gap-2 rounded-full px-3 py-1.5 transition hover:bg-background/70 hover:text-foreground"
                activeProps={{
                  className: "bg-background text-foreground shadow-sm",
                }}
                to="/receipts"
              >
                <ReceiptText className="size-4" />
                Receipts
              </Link>
            </div>
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Button size="sm" className="hidden sm:inline-flex" asChild>
              <Link to="/receipts">
                <ReceiptText className="size-4" />
                Upload receipt
              </Link>
            </Button>
            {loggedIn ? (
              <>
                {user?.email && (
                  <span className="hidden max-w-40 truncate rounded-full border border-border/70 px-3 py-1.5 text-sm text-muted-foreground xl:inline">
                    {user.email}
                  </span>
                )}
                <Button variant="ghost" size="icon-sm" asChild>
                  <Link to="/settings" aria-label="Settings">
                    <Settings className="size-4" />
                  </Link>
                </Button>
                <Button variant="outline" size="sm" onClick={logout}>
                  <LogOut className="size-4" />
                  <span className="hidden lg:inline">Log out</span>
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/login">
                    <LogIn className="size-4" />
                    Log in
                  </Link>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/signup">
                    <UserPlus className="size-4" />
                    Sign up
                  </Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  )
}

export default Layout
