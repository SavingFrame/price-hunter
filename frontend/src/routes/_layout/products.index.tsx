import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import {
  Barcode,
  ChevronRight,
  ImageIcon,
  PackageSearch,
  Search,
} from "lucide-react"
import { useEffect, useState } from "react"
import { z } from "zod"

import { type ProductPublic, ProductsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"

const productsSearchSchema = z.object({
  page: z.coerce.number().int().positive().optional().catch(undefined),
  q: z.string().optional().catch(undefined),
})

export const Route = createFileRoute("/_layout/products/")({
  component: ProductsPage,
  validateSearch: productsSearchSchema,
  head: () => ({
    meta: [
      {
        title: "Products - Cjenolovac",
      },
      {
        name: "description",
        content: "Search Croatian grocery products and compare shop prices.",
      },
    ],
  }),
})

const PAGE_SIZE = 100
const LAST_PRODUCTS_PATH_STORAGE_KEY = "products:last-path"
const PRODUCTS_FORCE_TOP_STORAGE_PREFIX = "products:force-top"
const PRODUCTS_RESTORE_ON_POP_STORAGE_KEY = "products:restore-on-pop"
const PRODUCTS_SELECTED_PRODUCT_STORAGE_PREFIX = "products:selected-product"

if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    window.sessionStorage.setItem(PRODUCTS_RESTORE_ON_POP_STORAGE_KEY, "true")
  })
}

function ProductsPage() {
  const { page: searchPage, q } = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const page = searchPage ?? 1
  const normalizedQuery = q?.trim() ?? ""
  const [search, setSearch] = useState(q ?? "")

  useEffect(() => {
    setSearch(q ?? "")
  }, [q])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const nextQuery = search.trim()

      if (nextQuery === normalizedQuery) {
        return
      }

      navigate({
        replace: true,
        search: (previous) => ({
          ...previous,
          page: undefined,
          q: nextQuery || undefined,
        }),
      })
    }, 300)

    return () => window.clearTimeout(timeoutId)
  }, [navigate, normalizedQuery, search])

  const { data, isPending, isError } = useQuery({
    queryKey: ["products", normalizedQuery, page],
    queryFn: () =>
      ProductsService.readProducts({
        limit: PAGE_SIZE,
        q: normalizedQuery || undefined,
        skip: (page - 1) * PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  })

  const products = data?.data ?? []
  const totalCount = data?.count ?? 0
  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) {
      navigate({
        replace: true,
        search: (previous) => ({
          ...previous,
          page: getPageSearchValue(totalPages),
        }),
      })
    }
  }, [navigate, page, totalPages])

  useEffect(() => {
    saveLastProductsPath()
  })

  useEffect(() => {
    if (isPending || isError) {
      return
    }

    if (shouldRestoreProductsPositionOnPopNavigation()) {
      restoreProductsPosition()
    }
  }, [isError, isPending])

  const handlePageChange = (nextPage: number) => {
    const nextProductsPath = getProductsPath(nextPage)

    markProductsPathForTopRestore(nextProductsPath)
    navigate({
      search: (previous) => ({
        ...previous,
        page: getPageSearchValue(nextPage),
      }),
    })
    window.scrollTo({ top: 0, behavior: "auto" })
  }

  return (
    <div className="space-y-8 pb-12">
      <section className="grid gap-6 lg:grid-cols-[1fr_0.7fr] lg:items-end">
        <div className="space-y-4">
          <Badge variant="secondary" className="gap-2 px-3 py-1">
            <PackageSearch className="size-3.5 text-primary" />
            Product catalog
          </Badge>
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
              Search products
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              Browse normalized grocery products. Search runs on the backend
              with full-text matching for names, brands, and categories.
            </p>
          </div>
        </div>

        <Card className="bg-card/80">
          <CardContent className="p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-12 rounded-2xl pl-10 text-base"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name, brand, category, or exact barcode..."
                value={search}
              />
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          label={normalizedQuery ? "Total matches" : "Total products"}
          value={totalCount.toString()}
        />
        <SummaryCard label="Shown" value={products.length.toString()} />
        <SummaryCard
          label="Page"
          value={totalPages > 0 ? `${page} / ${totalPages}` : "0 / 0"}
        />
      </section>

      {isPending && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              className="h-56 animate-pulse rounded-3xl border bg-card/70"
              key={index}
            />
          ))}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardHeader>
            <CardTitle>Could not load products</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Check that the backend is running and that the generated client uses
            the correct API URL.
          </CardContent>
        </Card>
      )}

      {!isPending && !isError && products.length === 0 && (
        <Card>
          <CardContent className="flex min-h-48 flex-col items-center justify-center gap-3 text-center">
            <PackageSearch className="size-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No products found</p>
              <p className="text-sm text-muted-foreground">
                Try a different product name, brand, category, or barcode.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!isPending && !isError && products.length > 0 && (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>

          <ProductsPagination
            currentPage={page}
            onPageChange={handlePageChange}
            pageSize={PAGE_SIZE}
            totalCount={totalCount}
          />
        </div>
      )}
    </div>
  )
}

function getPageSearchValue(page: number) {
  return page > 1 ? page : undefined
}

function getProductsPath(page?: number) {
  const searchParams = new URLSearchParams(window.location.search)

  if (page === undefined || page <= 1) {
    searchParams.delete("page")
  } else {
    searchParams.set("page", page.toString())
  }

  const search = searchParams.toString()
  return `${window.location.pathname}${search ? `?${search}` : ""}`
}

function getProductsScrollStorageKey(path = getProductsPath()) {
  return `products-scroll:${path}`
}

function getProductsForceTopStorageKey(path = getProductsPath()) {
  return `${PRODUCTS_FORCE_TOP_STORAGE_PREFIX}:${path}`
}

function getProductsSelectedProductStorageKey(path = getProductsPath()) {
  return `${PRODUCTS_SELECTED_PRODUCT_STORAGE_PREFIX}:${path}`
}

function saveLastProductsPath() {
  window.sessionStorage.setItem(
    LAST_PRODUCTS_PATH_STORAGE_KEY,
    getProductsPath(),
  )
}

function saveProductsScrollPosition(storageKey: string) {
  window.sessionStorage.setItem(storageKey, window.scrollY.toString())
}

function saveProductsListPosition(productId: string) {
  const productsPath = getProductsPath()

  saveLastProductsPath()
  saveProductsScrollPosition(getProductsScrollStorageKey(productsPath))
  window.sessionStorage.setItem(
    getProductsSelectedProductStorageKey(productsPath),
    productId,
  )
}

function markProductsPathForTopRestore(path: string) {
  window.sessionStorage.setItem(getProductsForceTopStorageKey(path), "true")
  window.sessionStorage.removeItem(getProductsSelectedProductStorageKey(path))
  window.sessionStorage.removeItem(getProductsScrollStorageKey(path))
}

function shouldRestoreProductsPositionOnPopNavigation() {
  const shouldRestore = window.sessionStorage.getItem(
    PRODUCTS_RESTORE_ON_POP_STORAGE_KEY,
  )

  window.sessionStorage.removeItem(PRODUCTS_RESTORE_ON_POP_STORAGE_KEY)
  return shouldRestore === "true"
}

function restoreProductsPosition() {
  const productsPath = getProductsPath()
  const forceTopStorageKey = getProductsForceTopStorageKey(productsPath)

  if (window.sessionStorage.getItem(forceTopStorageKey)) {
    window.sessionStorage.removeItem(forceTopStorageKey)
    requestScrollRestore(() => window.scrollTo({ top: 0, behavior: "auto" }))
    return
  }

  const selectedProductId = window.sessionStorage.getItem(
    getProductsSelectedProductStorageKey(productsPath),
  )

  if (selectedProductId) {
    requestScrollRestore(() => {
      const selectedProductElement = document.getElementById(
        getProductCardElementId(selectedProductId),
      )

      if (selectedProductElement) {
        selectedProductElement.scrollIntoView({
          block: "center",
          behavior: "auto",
        })
        return
      }

      restoreProductsScrollPosition(productsPath)
    })
    return
  }

  restoreProductsScrollPosition(productsPath)
}

function restoreProductsScrollPosition(productsPath: string) {
  const savedScrollY = window.sessionStorage.getItem(
    getProductsScrollStorageKey(productsPath),
  )

  if (!savedScrollY) {
    return
  }

  requestScrollRestore(() => {
    window.scrollTo({ top: Number(savedScrollY), behavior: "auto" })
  })
}

function requestScrollRestore(callback: () => void) {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(callback)
  })
}

function getProductCardElementId(productId: string) {
  return `product-card-${productId}`
}

type ProductsPaginationProps = {
  currentPage: number
  onPageChange: (page: number) => void
  pageSize: number
  totalCount: number
}

function ProductsPagination({
  currentPage,
  onPageChange,
  pageSize,
  totalCount,
}: ProductsPaginationProps) {
  const totalPages = Math.ceil(totalCount / pageSize)

  if (totalPages <= 1) {
    return null
  }

  const firstShown = (currentPage - 1) * pageSize + 1
  const lastShown = Math.min(currentPage * pageSize, totalCount)
  const pageItems = getPaginationItems(currentPage, totalPages)

  const goToPage = (nextPage: number) => {
    const boundedPage = Math.min(Math.max(nextPage, 1), totalPages)
    onPageChange(boundedPage)
  }

  return (
    <div className="flex flex-col items-center gap-4 border-t pt-6">
      <p className="text-sm text-muted-foreground">
        Showing {firstShown}-{lastShown} of {totalCount} products
      </p>
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              aria-disabled={currentPage === 1}
              className={
                currentPage === 1 ? "pointer-events-none opacity-50" : undefined
              }
              href="#"
              onClick={(event) => {
                event.preventDefault()
                goToPage(currentPage - 1)
              }}
            />
          </PaginationItem>

          {pageItems.map((item, index) => (
            <PaginationItem key={`${item}-${index}`}>
              {item === "ellipsis" ? (
                <PaginationEllipsis />
              ) : (
                <PaginationLink
                  href="#"
                  isActive={item === currentPage}
                  onClick={(event) => {
                    event.preventDefault()
                    goToPage(item)
                  }}
                >
                  {item}
                </PaginationLink>
              )}
            </PaginationItem>
          ))}

          <PaginationItem>
            <PaginationNext
              aria-disabled={currentPage === totalPages}
              className={
                currentPage === totalPages
                  ? "pointer-events-none opacity-50"
                  : undefined
              }
              href="#"
              onClick={(event) => {
                event.preventDefault()
                goToPage(currentPage + 1)
              }}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  )
}

function getPaginationItems(currentPage: number, totalPages: number) {
  const pages = new Set([1, totalPages])

  for (let page = currentPage - 1; page <= currentPage + 1; page += 1) {
    if (page > 1 && page < totalPages) {
      pages.add(page)
    }
  }

  const sortedPages = Array.from(pages).sort((a, b) => a - b)
  const items: Array<number | "ellipsis"> = []

  for (const page of sortedPages) {
    const previousItem = items[items.length - 1]
    if (typeof previousItem === "number" && page - previousItem > 1) {
      items.push("ellipsis")
    }
    items.push(page)
  }

  return items
}

type SummaryCardProps = {
  label: string
  value: string
}

function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <Card className="bg-card/70">
      <CardContent className="p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
      </CardContent>
    </Card>
  )
}

type ProductCardProps = {
  product: ProductPublic
}

function ProductCard({ product }: ProductCardProps) {
  return (
    <Link
      to="/products/$productId"
      params={{ productId: product.id }}
      className="group rounded-3xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      id={getProductCardElementId(product.id)}
      onClick={() => saveProductsListPosition(product.id)}
    >
      <Card className="h-full overflow-hidden bg-card/80 transition duration-200 group-hover:-translate-y-1 group-hover:border-primary/40 group-hover:shadow-xl group-hover:shadow-primary/5">
        <ProductImage imageUrl={product.image_url} name={product.name} />
        <CardContent className="space-y-4 p-5">
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {product.category && (
                <Badge variant="secondary">{product.category}</Badge>
              )}
              {product.brand && (
                <Badge variant="outline">{product.brand}</Badge>
              )}
            </div>
            <h2 className="line-clamp-2 text-lg font-semibold leading-snug">
              {product.name}
            </h2>
          </div>

          <div className="space-y-2 text-sm text-muted-foreground">
            <ProductMeta
              label="Latest price"
              value={formatOptionalCurrency(product.latest_price_eur)}
            />
            <ProductMeta label="Quantity" value={product.net_quantity} />
            <ProductMeta label="Unit" value={product.unit_of_measure} />
            {product.barcode && (
              <div className="flex items-center gap-2">
                <Barcode className="size-4" />
                <span className="truncate">{product.barcode}</span>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between border-t pt-4 text-sm font-medium text-primary">
            <span>Open details</span>
            <ChevronRight className="size-4 transition group-hover:translate-x-1" />
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

type ProductImageProps = {
  imageUrl?: string | null
  name: string
}

function ProductImage({ imageUrl, name }: ProductImageProps) {
  const [hasError, setHasError] = useState(false)

  if (imageUrl && !hasError) {
    return (
      <div className="flex h-36 items-center justify-center bg-muted/40">
        <img
          alt={name}
          className="h-full w-full object-contain p-4 transition duration-200 group-hover:scale-105"
          loading="lazy"
          onError={() => setHasError(true)}
          src={imageUrl}
        />
      </div>
    )
  }

  return (
    <div className="flex h-36 items-center justify-center bg-gradient-to-br from-primary/20 via-primary/10 to-background">
      <div className="flex size-20 items-center justify-center rounded-3xl bg-background/80 text-primary shadow-lg shadow-primary/10">
        <ImageIcon className="size-9" />
      </div>
    </div>
  )
}

type ProductMetaProps = {
  label: string
  value?: string | null
}

function ProductMeta({ label, value }: ProductMetaProps) {
  if (!value) {
    return null
  }

  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <span className="truncate font-medium text-foreground">{value}</span>
    </div>
  )
}

function formatOptionalCurrency(value?: string | null) {
  if (!value) {
    return undefined
  }

  return new Intl.NumberFormat("hr-HR", {
    currency: "EUR",
    style: "currency",
  }).format(Number(value))
}
