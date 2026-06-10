import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import {
  AlertTriangle,
  ArrowLeft,
  Barcode,
  CheckCircle2,
  CircleSlash,
  ImageIcon,
  ListChecks,
  PackageSearch,
  ReceiptText,
  Search,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import {
  ProductListsService,
  type ProductPublic,
  ProductsService,
  type ReceiptItemReviewPublic,
  type ReceiptPublic,
  ReceiptsService,
} from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout/receipts/$receiptId")({
  component: ReceiptDetailPage,
  head: () => ({
    meta: [
      {
        title: "Receipt review - Cjenolovac",
      },
    ],
  }),
})

function ReceiptDetailPage() {
  const { receiptId } = Route.useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [createListOpen, setCreateListOpen] = useState(false)

  const receiptQuery = useQuery({
    queryKey: ["receipts", receiptId],
    queryFn: () => ReceiptsService.readReceipt({ receiptId }),
  })

  const itemsQuery = useQuery({
    queryKey: ["receipts", receiptId, "items"],
    queryFn: () => ReceiptsService.readReceiptItems({ receiptId }),
  })

  const completeMutation = useMutation({
    mutationFn: () =>
      ReceiptsService.updateReceipt({
        receiptId,
        requestBody: { status: "completed" },
      }),
    onError: () => {
      showErrorToast("All receipt lines must be matched or skipped first.")
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["receipts"] }),
        queryClient.invalidateQueries({ queryKey: ["receipts", receiptId] }),
      ])
      showSuccessToast("Receipt completed.")
    },
  })

  const editMutation = useMutation({
    mutationFn: () =>
      ReceiptsService.updateReceipt({
        receiptId,
        requestBody: { status: "draft" },
      }),
    onError: () => {
      showErrorToast("Could not reopen receipt for editing.")
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["receipts"] }),
        queryClient.invalidateQueries({ queryKey: ["receipts", receiptId] }),
      ])
      showSuccessToast("Receipt reopened for editing.")
    },
  })

  const receipt = receiptQuery.data
  const items = itemsQuery.data ?? []
  const stats = useMemo(() => getReceiptStats(items), [items])
  const canComplete = stats.total > 0 && stats.open === 0
  const isCompleted = receipt?.status === "completed"

  if (receiptQuery.isPending) {
    return (
      <div className="space-y-6 pb-12">
        <div className="h-10 w-40 animate-pulse rounded-full bg-card" />
        <div className="h-96 animate-pulse rounded-3xl border bg-card/70" />
      </div>
    )
  }

  if (receiptQuery.isError || !receipt) {
    return (
      <ReceiptMessage
        description="Check that the receipt exists and belongs to your account."
        title="Could not load receipt"
      />
    )
  }

  return (
    <div className="space-y-8 pb-12">
      <Button variant="ghost" asChild>
        <Link to="/receipts">
          <ArrowLeft className="size-4" />
          Back to receipts
        </Link>
      </Button>

      <section className="grid gap-6 lg:grid-cols-[1fr_0.75fr]">
        <Card className="bg-card/80">
          <CardHeader className="gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="gap-2 px-3 py-1">
                <ReceiptText className="size-3.5 text-primary" />
                Receipt review
              </Badge>
              <Badge variant={isCompleted ? "default" : "secondary"}>
                {receipt.status ?? "draft"}
              </Badge>
            </div>
            <div className="space-y-3">
              <CardTitle className="text-3xl sm:text-5xl">
                SPAR receipt
              </CardTitle>
              <CardDescription className="text-base leading-7">
                Keep suggested products, choose better matches, or skip lines
                like bags and non-product receipt entries.
              </CardDescription>
            </div>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Review progress</CardTitle>
            <CardDescription>
              Complete when every line is matched or skipped.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <InfoTile label="Total" value={stats.total.toString()} />
              <InfoTile label="Matched" value={stats.matched.toString()} />
              <InfoTile label="Open" value={stats.open.toString()} />
            </div>
            <div className="rounded-2xl border bg-background/60 p-4 text-sm">
              <p className="text-muted-foreground">Receipt total</p>
              <p className="mt-1 text-2xl font-semibold">
                {formatCurrency(receipt.total_eur)}
              </p>
              <p className="mt-1 text-muted-foreground">
                {formatDateTime(receipt.purchase_datetime)}
              </p>
            </div>
            {isCompleted ? (
              <LoadingButton
                className="w-full"
                loading={editMutation.isPending}
                onClick={() => editMutation.mutate()}
                variant="outline"
              >
                <PackageSearch className="size-4" />
                Edit receipt
              </LoadingButton>
            ) : (
              <LoadingButton
                className="w-full"
                disabled={!canComplete}
                loading={completeMutation.isPending}
                onClick={() => completeMutation.mutate()}
              >
                <CheckCircle2 className="size-4" />
                Complete receipt
              </LoadingButton>
            )}
            <Button
              className="w-full"
              disabled={stats.matched === 0}
              onClick={() => setCreateListOpen(true)}
              variant="outline"
            >
              <ListChecks className="size-4" />
              Create product list
            </Button>
          </CardContent>
        </Card>
      </section>

      <CreateProductListFromReceiptDialog
        defaultName={buildDefaultListName(receipt)}
        onOpenChange={setCreateListOpen}
        onSuccess={(productList) => {
          setCreateListOpen(false)
          navigate({
            params: { productListId: productList.id },
            to: "/product-lists/$productListId",
          })
        }}
        open={createListOpen}
        receiptId={receiptId}
      />

      <Card>
        <CardHeader>
          <CardTitle>Receipt items</CardTitle>
          <CardDescription>
            Product search uses the existing catalog endpoint.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {itemsQuery.isPending && (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div
                  className="h-20 animate-pulse rounded-2xl border bg-background/60"
                  key={index}
                />
              ))}
            </div>
          )}

          {itemsQuery.isError && (
            <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
              Could not load receipt items.
            </div>
          )}

          {!itemsQuery.isPending &&
            !itemsQuery.isError &&
            items.length === 0 && (
              <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border bg-background/60 p-6 text-center">
                <ReceiptText className="size-10 text-muted-foreground" />
                <div>
                  <p className="font-medium">No receipt items</p>
                  <p className="text-sm text-muted-foreground">
                    This receipt does not have parsed lines yet.
                  </p>
                </div>
              </div>
            )}

          {!itemsQuery.isPending && items.length > 0 && (
            <ReceiptItemsTable
              disabled={isCompleted}
              items={items}
              receipt={receipt}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

type ReceiptItemsTableProps = {
  disabled: boolean
  items: Array<ReceiptItemReviewPublic>
  receipt: ReceiptPublic
}

function ReceiptItemsTable({
  disabled,
  items,
  receipt,
}: ReceiptItemsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-16">Line</TableHead>
          <TableHead>Receipt line</TableHead>
          <TableHead className="w-28">Qty</TableHead>
          <TableHead className="w-32">Total</TableHead>
          <TableHead className="min-w-80">Product</TableHead>
          <TableHead className="w-28">Skip</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <ReceiptItemRow
            disabled={disabled}
            item={item}
            key={item.id}
            receiptId={receipt.id ?? item.receipt_id}
          />
        ))}
      </TableBody>
    </Table>
  )
}

type ReceiptItemRowProps = {
  disabled: boolean
  item: ReceiptItemReviewPublic
  receiptId: string
}

function ReceiptItemRow({ disabled, item, receiptId }: ReceiptItemRowProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const updateMutation = useMutation({
    mutationFn: (requestBody: {
      product_id?: string | null
      is_skipped?: boolean
    }) =>
      ReceiptsService.updateReceiptItem({
        itemId: item.id,
        receiptId,
        requestBody,
      }),
    onError: () => {
      showErrorToast("Could not update receipt item.")
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["receipts", receiptId, "items"],
      })
    },
  })

  const isSkipped = item.is_skipped === true
  const isSaving = updateMutation.isPending
  const needsProduct = !item.product_id && !isSkipped

  return (
    <TableRow
      className={cn(
        isSkipped && "opacity-60",
        needsProduct && "bg-amber-500/5 hover:bg-amber-500/10",
      )}
    >
      <TableCell className="font-medium">#{item.line_number}</TableCell>
      <TableCell>
        <div className="min-w-64 space-y-1 whitespace-normal">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{item.raw_name}</p>
            {needsProduct && (
              <Badge
                variant="outline"
                className="border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-300"
              >
                <AlertTriangle className="size-3" />
                No product selected
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Unit price {formatOptionalCurrency(item.unit_price_eur)}
          </p>
        </div>
      </TableCell>
      <TableCell>
        {item.quantity}
        {item.unit_of_measure ? ` ${item.unit_of_measure}` : ""}
      </TableCell>
      <TableCell>{formatCurrency(item.line_total_eur)}</TableCell>
      <TableCell>
        <ProductPicker
          disabled={disabled || isSkipped || isSaving}
          item={item}
          onChange={(productId) =>
            updateMutation.mutate({ product_id: productId, is_skipped: false })
          }
        />
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Checkbox
            checked={isSkipped}
            disabled={disabled || isSaving}
            onCheckedChange={(checked) =>
              updateMutation.mutate({ is_skipped: checked === true })
            }
          />
          <span className="text-sm text-muted-foreground">Skip</span>
        </div>
      </TableCell>
    </TableRow>
  )
}

type ProductPickerProps = {
  disabled: boolean
  item: ReceiptItemReviewPublic
  onChange: (productId: string | null) => void
}

function ProductPicker({ disabled, item, onChange }: ProductPickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState(item.product?.name ?? item.raw_name)
  const debouncedSearch = useDebouncedValue(search, 300)
  const normalizedSearch = debouncedSearch.trim()
  const selectedProduct = item.product
  const hasProduct = Boolean(item.product_id && selectedProduct)

  useEffect(() => {
    if (!isOpen) {
      setSearch(item.product?.name ?? item.raw_name)
    }
  }, [isOpen, item.product, item.raw_name])

  const productsQuery = useQuery({
    enabled: isOpen,
    queryKey: ["products", "receipt-picker", normalizedSearch],
    queryFn: () =>
      ProductsService.readProducts({
        limit: 24,
        q: normalizedSearch || undefined,
      }),
  })

  const products = productsQuery.data?.data ?? []

  const handleSelect = (productId: string) => {
    onChange(productId)
    setIsOpen(false)
  }

  const handleClear = () => {
    onChange(null)
    setIsOpen(false)
  }

  return (
    <div className="min-w-80 space-y-3">
      {hasProduct && selectedProduct ? (
        <SelectedProductCard product={selectedProduct} />
      ) : (
        <div className="rounded-2xl border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
          <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertTriangle className="size-4" />
            No product selected
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Choose a catalog product or skip this receipt line.
          </p>
        </div>
      )}

      {!disabled && (
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => setIsOpen(true)}
            size="sm"
            type="button"
            variant={hasProduct ? "outline" : "default"}
          >
            <PackageSearch className="size-4" />
            {hasProduct ? "Change product" : "Choose product"}
          </Button>
          {hasProduct && (
            <Button
              onClick={handleClear}
              size="sm"
              type="button"
              variant="ghost"
            >
              Clear
            </Button>
          )}
        </div>
      )}

      <Sheet open={isOpen} onOpenChange={setIsOpen}>
        <SheetContent className="w-full overflow-hidden p-0 sm:max-w-3xl">
          <SheetHeader className="border-b p-6 pr-12">
            <SheetTitle>Choose product</SheetTitle>
            <SheetDescription>{`Search the catalog and select the best match for "${item.raw_name}".`}</SheetDescription>
          </SheetHeader>

          <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
            <div className="rounded-2xl border bg-card/70 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Receipt line
              </p>
              <p className="mt-1 font-medium">{item.raw_name}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {item.quantity}
                {item.unit_of_measure ? ` ${item.unit_of_measure}` : ""} ·{" "}
                {formatCurrency(item.line_total_eur)}
              </p>
            </div>

            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                autoFocus
                className="h-12 rounded-2xl pl-10 text-base"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name, brand, category, or barcode..."
                value={search}
              />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              {productsQuery.isPending && (
                <div className="grid gap-3 md:grid-cols-2">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <div
                      className="h-36 animate-pulse rounded-2xl border bg-card/70"
                      key={index}
                    />
                  ))}
                </div>
              )}

              {productsQuery.isError && (
                <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
                  Could not load products.
                </div>
              )}

              {!productsQuery.isPending &&
                !productsQuery.isError &&
                products.length === 0 && (
                  <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border bg-background/60 p-6 text-center">
                    <PackageSearch className="size-10 text-muted-foreground" />
                    <div>
                      <p className="font-medium">No products found</p>
                      <p className="text-sm text-muted-foreground">
                        Try a different product name, brand, category, or
                        barcode.
                      </p>
                    </div>
                  </div>
                )}

              {!productsQuery.isPending &&
                !productsQuery.isError &&
                products.length > 0 && (
                  <div className="grid gap-3 md:grid-cols-2">
                    {products.map((product) => (
                      <ProductPickerCard
                        isSelected={product.id === item.product_id}
                        key={product.id}
                        onSelect={() => handleSelect(product.id)}
                        product={product}
                      />
                    ))}
                  </div>
                )}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}

function SelectedProductCard({ product }: { product: ProductPublic }) {
  return (
    <Link
      className="flex gap-3 rounded-2xl border bg-background/60 p-3 transition hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      params={{ productId: product.id }}
      title="Open product details"
      to="/products/$productId"
    >
      <ProductThumb imageUrl={product.image_url} name={product.name} />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="line-clamp-2 text-sm font-medium">{product.name}</p>
        <div className="flex flex-wrap gap-1">
          {product.brand && <Badge variant="outline">{product.brand}</Badge>}
          {product.category && (
            <Badge variant="secondary">{product.category}</Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {[product.net_quantity, product.unit_of_measure]
            .filter(Boolean)
            .join(" ")}
        </p>
      </div>
    </Link>
  )
}

type ProductPickerCardProps = {
  isSelected: boolean
  onSelect: () => void
  product: ProductPublic
}

function ProductPickerCard({
  isSelected,
  onSelect,
  product,
}: ProductPickerCardProps) {
  return (
    <div
      className={cn(
        "group flex gap-4 rounded-2xl border bg-card/80 p-4 text-left transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg",
        isSelected && "border-primary bg-primary/5",
      )}
    >
      <ProductThumb imageUrl={product.image_url} name={product.name} />
      <div className="min-w-0 flex-1 space-y-3">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {product.category && (
              <Badge variant="secondary">{product.category}</Badge>
            )}
            {product.brand && <Badge variant="outline">{product.brand}</Badge>}
            {isSelected && <Badge>Selected</Badge>}
          </div>
          <p className="line-clamp-2 font-semibold leading-snug">
            {product.name}
          </p>
        </div>

        <div className="space-y-1 text-sm text-muted-foreground">
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

        <div className="flex flex-wrap gap-2 border-t pt-3">
          <Button onClick={onSelect} size="sm" type="button">
            {isSelected ? "Use selected" : "Select"}
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link params={{ productId: product.id }} to="/products/$productId">
              Open details
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

type ProductThumbProps = {
  imageUrl?: string | null
  name: string
}

function ProductThumb({ imageUrl, name }: ProductThumbProps) {
  const [hasError, setHasError] = useState(false)

  if (imageUrl && !hasError) {
    return (
      <div className="flex size-20 shrink-0 items-center justify-center rounded-xl bg-muted/40">
        <img
          alt={name}
          className="h-full w-full object-contain p-2"
          loading="lazy"
          onError={() => setHasError(true)}
          src={imageUrl}
        />
      </div>
    )
  }

  return (
    <div className="flex size-20 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 via-primary/10 to-background text-primary">
      <ImageIcon className="size-8" />
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

function useDebouncedValue(value: string, delayMs: number) {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedValue(value), delayMs)

    return () => window.clearTimeout(timeoutId)
  }, [delayMs, value])

  return debouncedValue
}

type ReceiptStats = {
  matched: number
  open: number
  skipped: number
  total: number
}

function getReceiptStats(items: Array<ReceiptItemReviewPublic>): ReceiptStats {
  const skipped = items.filter((item) => item.is_skipped).length
  const matched = items.filter(
    (item) => item.product_id && !item.is_skipped,
  ).length
  return {
    matched,
    open: items.length - matched - skipped,
    skipped,
    total: items.length,
  }
}

type InfoTileProps = {
  label: string
  value: string
}

function InfoTile({ label, value }: InfoTileProps) {
  return (
    <div className="rounded-2xl border bg-background/60 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}

type ReceiptMessageProps = {
  description: string
  title: string
}

function ReceiptMessage({ description, title }: ReceiptMessageProps) {
  return (
    <div className="space-y-6 pb-12">
      <Button variant="ghost" asChild>
        <Link to="/receipts">
          <ArrowLeft className="size-4" />
          Back to receipts
        </Link>
      </Button>
      <Card>
        <CardContent className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
          <CircleSlash className="size-10 text-muted-foreground" />
          <div>
            <p className="font-medium">{title}</p>
            <p className="max-w-md text-sm text-muted-foreground">
              {description}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "Unknown date"
  }

  return new Intl.DateTimeFormat("hr-HR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function formatCurrency(value?: string | null) {
  if (!value) {
    return "Not available"
  }

  return new Intl.NumberFormat("hr-HR", {
    currency: "EUR",
    style: "currency",
  }).format(Number(value))
}

function formatOptionalCurrency(value?: string | null) {
  return value ? formatCurrency(value) : "Not available"
}

type CreateProductListFromReceiptDialogProps = {
  defaultName: string
  onOpenChange: (open: boolean) => void
  onSuccess: (productList: { id: string }) => void
  open: boolean
  receiptId: string
}

function CreateProductListFromReceiptDialog({
  defaultName,
  onOpenChange,
  onSuccess,
  open,
  receiptId,
}: CreateProductListFromReceiptDialogProps) {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [name, setName] = useState(defaultName)
  const [description, setDescription] = useState("")

  useEffect(() => {
    if (open) {
      setName(defaultName)
      setDescription("")
    }
  }, [defaultName, open])

  const createMutation = useMutation({
    mutationFn: () =>
      ProductListsService.createProductListFromReceipt({
        receiptId,
        requestBody: {
          description: description.trim() || null,
          name: name.trim(),
        },
      }),
    onError: () => {
      showErrorToast(
        "Could not create product list. Make sure the name is unique and the receipt has matched items.",
      )
    },
    onSuccess: (productList) => {
      showSuccessToast("Product list created from receipt.")
      onSuccess(productList)
    },
  })

  const canCreate = name.trim().length > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create product list from receipt</DialogTitle>
          <DialogDescription>
            All matched, non-skipped lines will be added as products.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="from-receipt-list-name">Name</Label>
            <Input
              id="from-receipt-list-name"
              onChange={(event) => setName(event.target.value)}
              placeholder="Weekly groceries"
              value={name}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="from-receipt-list-description">Description</Label>
            <Input
              id="from-receipt-list-description"
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional note"
              value={description}
            />
          </div>
        </div>
        <DialogFooter>
          <LoadingButton
            disabled={!canCreate}
            loading={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            <ListChecks className="size-4" />
            Create list
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function buildDefaultListName(receipt?: ReceiptPublic | null) {
  if (!receipt?.purchase_datetime) {
    return "Receipt list"
  }

  const date = new Intl.DateTimeFormat("hr-HR", { dateStyle: "medium" }).format(
    new Date(receipt.purchase_datetime),
  )
  return `Receipt — ${date}`
}
