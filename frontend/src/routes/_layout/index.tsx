import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeEuro,
  Clock3,
  ImageIcon,
  type LucideIcon,
  PackageOpen,
  ReceiptText,
  Search,
  Sparkles,
  Store,
} from "lucide-react"

import { DashboardService, type PriceMover } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const PRICE_MOVER_LIMIT = 8

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Cjenolovac dashboard",
      },
      {
        name: "description",
        content:
          "Find Croatian grocery products, compare shop prices, and optimize baskets.",
      },
    ],
  }),
})

function Dashboard() {
  const priceMoversQuery = useQuery({
    queryKey: ["dashboard", "price-movers", PRICE_MOVER_LIMIT],
    queryFn: () =>
      DashboardService.readPriceMovers({ limit: PRICE_MOVER_LIMIT }),
  })
  const priceMovers = priceMoversQuery.data
  const dateRange = formatDateRange(
    priceMovers?.previous_date,
    priceMovers?.current_date,
  )
  const biggestDrop = priceMovers?.price_drops[0]
  const biggestIncrease = priceMovers?.price_increases[0]

  return (
    <div className="space-y-8 pb-12">
      <section className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr] lg:items-stretch">
        <Card className="relative overflow-hidden border-primary/20 bg-card/80 shadow-2xl shadow-primary/5">
          <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-primary/15 blur-3xl" />
          <CardHeader className="relative gap-5 p-6 sm:p-8">
            <Badge variant="secondary" className="w-fit gap-2 px-3 py-1">
              <Sparkles className="size-3.5 text-primary" />
              Live price radar
            </Badge>
            <div className="max-w-2xl space-y-4">
              <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
                Find what got cheaper before you shop.
              </h1>
              <p className="text-base leading-7 text-muted-foreground sm:text-lg">
                Track grocery price changes across Croatian retailers, browse
                normalized products, and open details with shop price history.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button size="lg" asChild>
                <a href="#price-movers">
                  <ArrowDownRight className="size-4" />
                  See price drops
                </a>
              </Button>
              <Button variant="outline" size="lg" asChild>
                <Link to="/products">
                  <Search className="size-4" />
                  Browse products
                </Link>
              </Button>
            </div>
          </CardHeader>
        </Card>

        <Card id="products" className="border-border/70 bg-card/70 shadow-xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Search className="size-5 text-primary" />
              Product search
            </CardTitle>
            <CardDescription>
              Find normalized products, then open a detail page with shop prices
              and history.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-2xl border bg-background/70 p-4">
              <p className="text-sm text-muted-foreground">Search products</p>
              <p className="mt-1 text-xl font-medium">
                milk, eggs, bread, rice...
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <MetricCard
                icon={PackageOpen}
                label="Price drops"
                value={formatCount(priceMovers?.price_drops.length)}
              />
              <MetricCard
                icon={ArrowUpRight}
                label="Price increases"
                value={formatCount(priceMovers?.price_increases.length)}
              />
              <MetricCard
                icon={BadgeEuro}
                label="Biggest drop"
                value={
                  biggestDrop
                    ? formatSignedPercent(biggestDrop.percent_change)
                    : "Loading"
                }
              />
              <MetricCard
                icon={Clock3}
                label="Compared days"
                value={dateRange ?? "Loading"}
              />
            </div>
          </CardContent>
        </Card>
      </section>

      <section
        id="price-movers"
        className="grid gap-6 lg:grid-cols-[1fr_0.7fr]"
      >
        <Card className="bg-card/80">
          <CardHeader>
            <CardTitle>Biggest price moves</CardTitle>
            <CardDescription>
              Products with the largest average retailer price changes between
              the latest two complete import days.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PriceMoversTabs
              isError={priceMoversQuery.isError}
              isPending={priceMoversQuery.isPending}
              priceDrops={priceMovers?.price_drops ?? []}
              priceIncreases={priceMovers?.price_increases ?? []}
            />
          </CardContent>
        </Card>

        <Card className="bg-card/80">
          <CardHeader>
            <CardTitle>What changed?</CardTitle>
            <CardDescription>
              A quick read on the latest complete data refresh.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoTile
              icon={Clock3}
              label="Compared period"
              value={dateRange ?? "Not available"}
            />
            <InfoTile
              icon={ArrowDownRight}
              label="Best deal spotted"
              value={
                biggestDrop
                  ? `${biggestDrop.retailer.name}, ${formatSignedCurrency(biggestDrop.absolute_change_eur)}`
                  : "Not available"
              }
            />
            <InfoTile
              icon={ArrowUpRight}
              label="Biggest increase"
              value={
                biggestIncrease
                  ? `${biggestIncrease.retailer.name}, ${formatSignedCurrency(biggestIncrease.absolute_change_eur)}`
                  : "Not available"
              }
            />
            <Button className="w-full" variant="outline" asChild>
              <Link to="/products">
                <Search className="size-4" />
                Search all products
              </Link>
            </Button>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>How this works</CardTitle>
            <CardDescription>
              We compare the same retailer product on the latest two complete
              import days, using average price across that retailer's stores.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <InfoTile
              icon={Store}
              label="Fair retailer scope"
              value="Same retailer and product"
            />
            <InfoTile
              icon={BadgeEuro}
              label="Price metric"
              value="Average store price"
            />
            <InfoTile
              icon={Clock3}
              label="Freshness rule"
              value="Latest complete days"
            />
          </CardContent>
        </Card>

        <Card
          id="receipts"
          className="border-primary/20 bg-primary text-primary-foreground"
        >
          <CardHeader>
            <CardTitle>Next feature</CardTitle>
            <CardDescription className="text-primary-foreground/75">
              Receipt upload can become the bridge from past shopping to today's
              comparison.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-2xl bg-primary-foreground/10 p-4">
              <ReceiptText className="mb-4 size-8" />
              <p className="text-sm leading-6 text-primary-foreground/85">
                Upload a bill, extract products and quantities, then compare the
                same basket against current shop prices.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}

type PriceMoversTabsProps = {
  isError: boolean
  isPending: boolean
  priceDrops: Array<PriceMover>
  priceIncreases: Array<PriceMover>
}

function PriceMoversTabs({
  isError,
  isPending,
  priceDrops,
  priceIncreases,
}: PriceMoversTabsProps) {
  return (
    <Tabs defaultValue="drops" className="gap-4">
      <TabsList>
        <TabsTrigger value="drops">
          <ArrowDownRight className="size-4" />
          Drops
        </TabsTrigger>
        <TabsTrigger value="increases">
          <ArrowUpRight className="size-4" />
          Increases
        </TabsTrigger>
      </TabsList>
      <TabsContent value="drops">
        <PriceMoverList
          emptyMessage="No price drops found for the compared days."
          isError={isError}
          isPending={isPending}
          movers={priceDrops}
          trend="down"
        />
      </TabsContent>
      <TabsContent value="increases">
        <PriceMoverList
          emptyMessage="No price increases found for the compared days."
          isError={isError}
          isPending={isPending}
          movers={priceIncreases}
          trend="up"
        />
      </TabsContent>
    </Tabs>
  )
}

type PriceMoverListProps = {
  emptyMessage: string
  isError: boolean
  isPending: boolean
  movers: Array<PriceMover>
  trend: "down" | "up"
}

function PriceMoverList({
  emptyMessage,
  isError,
  isPending,
  movers,
  trend,
}: PriceMoverListProps) {
  if (isPending) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            className="h-24 animate-pulse rounded-2xl border bg-background/60"
            key={index}
          />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
        Could not load price movers. Check that the backend is running.
      </div>
    )
  }

  if (movers.length === 0) {
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border bg-background/60 p-6 text-center">
        <BadgeEuro className="size-10 text-muted-foreground" />
        <div>
          <p className="font-medium">No price movers</p>
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {movers.map((mover) => (
        <PriceMoverRow
          key={`${mover.retailer.id}-${mover.product.id}-${mover.current_date}`}
          mover={mover}
          trend={trend}
        />
      ))}
    </div>
  )
}

type PriceMoverRowProps = {
  mover: PriceMover
  trend: "down" | "up"
}

function PriceMoverRow({ mover, trend }: PriceMoverRowProps) {
  const isDrop = trend === "down"
  const Icon = isDrop ? ArrowDownRight : ArrowUpRight

  return (
    <Link
      className="grid gap-4 rounded-2xl border bg-background/60 p-4 transition hover:border-primary/40 hover:bg-background sm:grid-cols-[auto_1fr_auto] sm:items-center"
      params={{ productId: mover.product.id }}
      to="/products/$productId"
    >
      <ProductThumb
        imageUrl={mover.product.image_url}
        name={mover.product.name}
      />
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="line-clamp-1 font-medium">{mover.product.name}</p>
          <Badge variant="secondary">{mover.retailer.name}</Badge>
          {mover.product.category && (
            <Badge variant="outline">{mover.product.category}</Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          {formatCurrency(mover.previous_price_eur)} to{" "}
          {formatCurrency(mover.current_price_eur)}
        </p>
      </div>
      <div className="flex items-center justify-between gap-4 sm:justify-end">
        <div className="text-left sm:text-right">
          <p
            className={
              isDrop
                ? "text-xl font-semibold text-primary"
                : "text-xl font-semibold text-destructive"
            }
          >
            {formatSignedPercent(mover.percent_change)}
          </p>
          <p className="text-sm text-muted-foreground">
            {formatSignedCurrency(mover.absolute_change_eur)}
          </p>
        </div>
        <Icon
          className={isDrop ? "size-5 text-primary" : "size-5 text-destructive"}
        />
      </div>
    </Link>
  )
}

type ProductThumbProps = {
  imageUrl?: string | null
  name: string
}

function ProductThumb({ imageUrl, name }: ProductThumbProps) {
  if (imageUrl) {
    return (
      <div className="flex size-16 items-center justify-center overflow-hidden rounded-2xl border bg-muted/40">
        <img
          alt={name}
          className="h-full w-full object-contain p-2"
          loading="lazy"
          src={imageUrl}
        />
      </div>
    )
  }

  return (
    <div className="flex size-16 items-center justify-center rounded-2xl border bg-muted/40 text-muted-foreground">
      <ImageIcon className="size-6" />
    </div>
  )
}

type MetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
}

function MetricCard({ icon: Icon, label, value }: MetricCardProps) {
  return (
    <div className="rounded-2xl border bg-background/60 p-4">
      <Icon className="mb-3 size-5 text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  )
}

type InfoTileProps = {
  icon: LucideIcon
  label: string
  value: string
}

function InfoTile({ icon: Icon, label, value }: InfoTileProps) {
  return (
    <div className="rounded-2xl border bg-background/60 p-4">
      <Icon className="mb-3 size-5 text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 font-semibold">{value}</p>
    </div>
  )
}

function formatCount(value?: number) {
  if (value === undefined) {
    return "Loading"
  }

  return new Intl.NumberFormat("hr-HR").format(value)
}

function formatDateRange(
  previousDate?: string | null,
  currentDate?: string | null,
) {
  if (!previousDate || !currentDate) {
    return undefined
  }

  return `${formatShortDate(previousDate)} to ${formatShortDate(currentDate)}`
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("hr-HR", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(value))
}

function formatCurrency(value: string) {
  return new Intl.NumberFormat("hr-HR", {
    currency: "EUR",
    style: "currency",
  }).format(Number(value))
}

function formatSignedCurrency(value: string) {
  const numericValue = Number(value)
  const sign = numericValue > 0 ? "+" : ""

  return `${sign}${formatCurrency(value)}`
}

function formatSignedPercent(value: string) {
  const numericValue = Number(value)
  const sign = numericValue > 0 ? "+" : ""

  return `${sign}${numericValue.toFixed(1)}%`
}
