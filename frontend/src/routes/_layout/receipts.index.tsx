import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import {
  CalendarClock,
  FileText,
  ReceiptText,
  Trash2,
  Upload,
} from "lucide-react"
import { useState } from "react"

import { type ReceiptPublic, ReceiptsService } from "@/client"
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
  DialogClose,
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

const SPAR_RETAILER_ID = "019dd1b1-dafb-7015-973e-90e630409a7a"

export const Route = createFileRoute("/_layout/receipts/")({
  component: ReceiptsPage,
  head: () => ({
    meta: [
      {
        title: "Receipts - Cjenolovac",
      },
      {
        name: "description",
        content: "Upload and review grocery receipts.",
      },
    ],
  }),
})

function ReceiptsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate({ from: Route.fullPath })
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [file, setFile] = useState<File | null>(null)

  const receiptsQuery = useQuery({
    queryKey: ["receipts"],
    queryFn: () => ReceiptsService.readReceipts({ limit: 100 }),
  })

  const uploadMutation = useMutation({
    mutationFn: (selectedFile: File) =>
      ReceiptsService.createReceipt({
        formData: {
          file: selectedFile,
          retailer_id: SPAR_RETAILER_ID,
        },
      }),
    onError: () => {
      showErrorToast("Could not upload receipt.")
    },
    onSuccess: async (receipt) => {
      await queryClient.invalidateQueries({ queryKey: ["receipts"] })
      showSuccessToast("Receipt uploaded and parsed.")
      if (receipt.id) {
        navigate({
          params: { receiptId: receipt.id },
          to: "/receipts/$receiptId",
        })
      }
    },
  })

  const receipts = receiptsQuery.data?.data ?? []

  const handleUpload = () => {
    if (!file) {
      showErrorToast("Choose a PDF receipt first.")
      return
    }

    uploadMutation.mutate(file)
  }

  return (
    <div className="space-y-8 pb-12">
      <section className="grid gap-6 lg:grid-cols-[1fr_0.75fr] lg:items-stretch">
        <div className="space-y-4">
          <Badge variant="secondary" className="gap-2 px-3 py-1">
            <ReceiptText className="size-3.5 text-primary" />
            Receipt import
          </Badge>
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
              Upload receipts
            </h1>
            <p className="max-w-2xl text-base leading-7 text-muted-foreground">
              Upload a SPAR PDF receipt, review matched products, skip lines you
              do not need, and complete the receipt when every line is handled.
            </p>
          </div>
        </div>

        <Card className="bg-card/80">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="size-5 text-primary" />
              New receipt
            </CardTitle>
            <CardDescription>
              SPAR is the only supported retailer for the first version.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="receipt-file">PDF file</Label>
              <Input
                accept="application/pdf,.pdf"
                id="receipt-file"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                type="file"
              />
            </div>
            <div className="rounded-2xl border bg-background/60 p-4 text-sm">
              <p className="font-medium">Retailer</p>
              <p className="text-muted-foreground">SPAR / Interspar</p>
            </div>
            <LoadingButton
              className="w-full"
              loading={uploadMutation.isPending}
              onClick={handleUpload}
            >
              <Upload className="size-4" />
              Upload and parse
            </LoadingButton>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Receipt history</CardTitle>
          <CardDescription>
            Open a draft receipt to continue product review.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {receiptsQuery.isPending && (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  className="h-24 animate-pulse rounded-2xl border bg-background/60"
                  key={index}
                />
              ))}
            </div>
          )}

          {receiptsQuery.isError && (
            <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-muted-foreground">
              Could not load receipts.
            </div>
          )}

          {!receiptsQuery.isPending &&
            !receiptsQuery.isError &&
            receipts.length === 0 && (
              <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border bg-background/60 p-6 text-center">
                <ReceiptText className="size-10 text-muted-foreground" />
                <div>
                  <p className="font-medium">No receipts yet</p>
                  <p className="text-sm text-muted-foreground">
                    Upload your first SPAR receipt to start reviewing items.
                  </p>
                </div>
              </div>
            )}

          {!receiptsQuery.isPending && receipts.length > 0 && (
            <div className="space-y-3">
              {receipts.map((receipt) => (
                <ReceiptRow key={receipt.id} receipt={receipt} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

type ReceiptRowProps = {
  receipt: ReceiptPublic
}

function ReceiptRow({ receipt }: ReceiptRowProps) {
  return (
    <div className="grid gap-4 rounded-2xl border bg-background/60 p-4 transition hover:border-primary/40 hover:bg-background sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <Link
        className="flex size-14 items-center justify-center rounded-2xl border bg-muted/40 text-primary"
        params={{ receiptId: receipt.id }}
        to="/receipts/$receiptId"
      >
        <FileText className="size-6" />
      </Link>
      <Link
        className="min-w-0 space-y-2"
        params={{ receiptId: receipt.id }}
        to="/receipts/$receiptId"
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">SPAR receipt</p>
          <Badge
            variant={receipt.status === "completed" ? "default" : "secondary"}
          >
            {receipt.status ?? "draft"}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-3 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <CalendarClock className="size-4" />
            {formatDateTime(receipt.purchase_datetime)}
          </span>
          <span>Total {formatCurrency(receipt.total_eur)}</span>
        </div>
      </Link>
      <div className="flex flex-wrap gap-2 sm:justify-end">
        <Button asChild variant="outline">
          <Link params={{ receiptId: receipt.id }} to="/receipts/$receiptId">
            Review
          </Link>
        </Button>
        <DeleteReceiptButton receiptId={receipt.id} />
      </div>
    </div>
  )
}

function DeleteReceiptButton({ receiptId }: { receiptId: string }) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [isOpen, setIsOpen] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: () => ReceiptsService.deleteReceipt({ receiptId }),
    onError: () => {
      showErrorToast("Could not delete receipt.")
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["receipts"] })
      showSuccessToast("Receipt deleted.")
      setIsOpen(false)
    },
  })

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button size="icon" title="Delete receipt" variant="destructive">
          <Trash2 className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete receipt</DialogTitle>
          <DialogDescription>
            This receipt and its parsed lines will be permanently deleted. This
            action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button disabled={deleteMutation.isPending} variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton
            loading={deleteMutation.isPending}
            onClick={() => deleteMutation.mutate()}
            variant="destructive"
          >
            Delete
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
