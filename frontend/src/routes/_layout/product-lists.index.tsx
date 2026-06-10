import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { ChevronRight, ListChecks, Plus, Trash2 } from "lucide-react"
import { useState } from "react"

import { type ProductListPublic, ProductListsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"

export const Route = createFileRoute("/_layout/product-lists/")({
  component: ProductListsPage,
  head: () => ({
    meta: [
      {
        title: "Product lists - Cjenolovac",
      },
      {
        name: "description",
        content: "Create reusable grocery lists and compare product prices.",
      },
    ],
  }),
})

function ProductListsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate({ from: Route.fullPath })
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const listsQuery = useQuery({
    queryKey: ["product-lists"],
    queryFn: () => ProductListsService.readProductLists({ limit: 100 }),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      ProductListsService.createProductList({
        requestBody: {
          description: description.trim() || null,
          name: name.trim(),
        },
      }),
    onError: () => {
      showErrorToast("Could not create product list.")
    },
    onSuccess: async (productList) => {
      await queryClient.invalidateQueries({ queryKey: ["product-lists"] })
      showSuccessToast("Product list created.")
      setOpen(false)
      setName("")
      setDescription("")
      navigate({
        params: { productListId: productList.id },
        to: "/product-lists/$productListId",
      })
    },
  })

  const productLists = listsQuery.data?.data ?? []
  const canCreate = name.trim().length > 0

  return (
    <div className="space-y-8 pb-12">
      <section className="grid gap-6 lg:grid-cols-[1fr_0.75fr] lg:items-stretch">
        <div className="space-y-4">
          <Badge variant="secondary" className="gap-2 px-3 py-1">
            <ListChecks className="size-3.5 text-primary" />
            Product lists
          </Badge>
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
              Build reusable baskets
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              Save canonical products into weekly lists, then use those lists
              for price comparisons and basket insights.
            </p>
          </div>
        </div>

        <Card className="bg-card/80">
          <CardHeader>
            <CardTitle>Create a list</CardTitle>
            <CardDescription>
              Start with a name, then add products from search or product detail
              pages.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CreateProductListDialog
              canCreate={canCreate}
              createMutationPending={createMutation.isPending}
              description={description}
              name={name}
              onCreate={() => createMutation.mutate()}
              onDescriptionChange={setDescription}
              onNameChange={setName}
              open={open}
              setOpen={setOpen}
            />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Your product lists</CardTitle>
          <CardDescription>
            Open a list to add products, edit quantities, or remove items.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {listsQuery.isPending && (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  className="h-24 animate-pulse rounded-2xl border bg-background/60"
                  key={index}
                />
              ))}
            </div>
          )}

          {listsQuery.isError && (
            <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
              Could not load product lists.
            </div>
          )}

          {!listsQuery.isPending &&
            !listsQuery.isError &&
            productLists.length === 0 && (
              <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border bg-background/60 p-6 text-center">
                <ListChecks className="size-10 text-muted-foreground" />
                <div>
                  <p className="font-medium">No product lists yet</p>
                  <p className="text-sm text-muted-foreground">
                    Create your first list to start building a reusable basket.
                  </p>
                </div>
              </div>
            )}

          {!listsQuery.isPending && productLists.length > 0 && (
            <div className="space-y-3">
              {productLists.map((productList) => (
                <ProductListRow
                  key={productList.id}
                  productList={productList}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

type CreateProductListDialogProps = {
  canCreate: boolean
  createMutationPending: boolean
  description: string
  name: string
  onCreate: () => void
  onDescriptionChange: (value: string) => void
  onNameChange: (value: string) => void
  open: boolean
  setOpen: (open: boolean) => void
}

function CreateProductListDialog({
  canCreate,
  createMutationPending,
  description,
  name,
  onCreate,
  onDescriptionChange,
  onNameChange,
  open,
  setOpen,
}: CreateProductListDialogProps) {
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="w-full">
          <Plus className="size-4" />
          New product list
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New product list</DialogTitle>
          <DialogDescription>
            Create a reusable basket, for example weekly groceries.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="product-list-name">Name</Label>
            <Input
              id="product-list-name"
              onChange={(event) => onNameChange(event.target.value)}
              placeholder="Weekly groceries"
              value={name}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="product-list-description">Description</Label>
            <Input
              id="product-list-description"
              onChange={(event) => onDescriptionChange(event.target.value)}
              placeholder="Optional note"
              value={description}
            />
          </div>
        </div>
        <DialogFooter>
          <LoadingButton
            disabled={!canCreate}
            loading={createMutationPending}
            onClick={onCreate}
          >
            <Plus className="size-4" />
            Create list
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type ProductListRowProps = {
  productList: ProductListPublic
}

function ProductListRow({ productList }: ProductListRowProps) {
  return (
    <div className="grid gap-4 rounded-2xl border bg-background/60 p-4 transition hover:border-primary/40 hover:bg-background sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <Link
        className="flex size-14 items-center justify-center rounded-2xl border bg-muted/40 text-primary"
        params={{ productListId: productList.id }}
        to="/product-lists/$productListId"
      >
        <ListChecks className="size-6" />
      </Link>
      <Link
        className="min-w-0 space-y-1"
        params={{ productListId: productList.id }}
        to="/product-lists/$productListId"
      >
        <p className="truncate font-medium">{productList.name}</p>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {productList.description || "No description"}
        </p>
      </Link>
      <div className="flex items-center justify-end gap-2">
        <DeleteProductListButton productList={productList} />
        <Button variant="outline" size="sm" asChild>
          <Link
            params={{ productListId: productList.id }}
            to="/product-lists/$productListId"
          >
            Open
            <ChevronRight className="size-4" />
          </Link>
        </Button>
      </div>
    </div>
  )
}

type DeleteProductListButtonProps = {
  productList: ProductListPublic
}

function DeleteProductListButton({
  productList,
}: DeleteProductListButtonProps) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const deleteMutation = useMutation({
    mutationFn: () =>
      ProductListsService.deleteProductList({ productListId: productList.id }),
    onError: () => {
      showErrorToast("Could not delete product list.")
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["product-lists"] })
      showSuccessToast("Product list deleted.")
    },
  })

  return (
    <Button
      aria-label={`Delete ${productList.name}`}
      disabled={deleteMutation.isPending}
      onClick={() => deleteMutation.mutate()}
      size="icon"
      variant="ghost"
    >
      <Trash2 className="size-4" />
    </Button>
  )
}
