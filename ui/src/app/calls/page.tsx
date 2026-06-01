"use client";

import { format } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Filter,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  Search,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type CallStatus = "answered" | "missed" | "failed" | "active";
type Direction = "inbound" | "outbound";

interface CallRecord {
  id: string;
  callSid: string;
  from: string;
  to: string;
  direction: Direction;
  duration: number;
  status: CallStatus;
  cost: number;
  timestamp: Date;
}

function randomSid() {
  return "CA" + Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
}

const ALL_CALLS: CallRecord[] = Array.from({ length: 87 }, (_, i) => {
  const statuses: CallStatus[] = ["answered", "answered", "answered", "missed", "failed", "active"];
  const dirs: Direction[] = ["inbound", "outbound"];
  const froms = [
    "+14155551234", "+12125559876", "+13105550123", "+16175551234",
    "+17205550123", "+18085551234", "+19045550123", "+14155554321",
  ];
  const tos = [
    "+918765432109", "+919876543210", "+917654321098", "+916543210987",
    "+915432109876", "+919812345678", "+918877665544", "+919011223344",
  ];
  return {
    id: `call-${i}`,
    callSid: randomSid(),
    from: froms[i % froms.length],
    to: tos[i % tos.length],
    direction: dirs[i % 2],
    duration: Math.floor(Math.random() * 600) + 5,
    status: statuses[i % statuses.length],
    cost: +(Math.random() * 0.5 + 0.005).toFixed(4),
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * (i * 0.7 + 0.5)),
  };
});

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s < 10 ? "0" : ""}${s}s`;
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

function statusBadge(status: CallStatus) {
  const map: Record<CallStatus, { label: string; class: string }> = {
    answered: {
      label: "Answered",
      class:
        "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    },
    missed: {
      label: "Missed",
      class: "border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400",
    },
    failed: {
      label: "Failed",
      class:
        "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    },
    active: {
      label: "Active",
      class: "border-blue-500/20 bg-blue-500/10 text-blue-600 dark:text-blue-400",
    },
  };
  const s = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none",
        s.class,
      )}
    >
      {status === "active" && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
        </span>
      )}
      {s.label}
    </span>
  );
}

const PAGE_SIZE = 15;

export default function CallsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [directionFilter, setDirectionFilter] = useState<string>("all");
  const [dateRange, setDateRange] = useState<{ from: Date | undefined; to: Date | undefined }>({
    from: undefined,
    to: undefined,
  });
  const [page, setPage] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 500);
    return () => clearTimeout(timer);
  }, []);

  const filtered = useMemo(() => {
    let list = ALL_CALLS;

    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.callSid.toLowerCase().includes(q) ||
          c.from.includes(q) ||
          c.to.includes(q),
      );
    }

    if (statusFilter !== "all") {
      list = list.filter((c) => c.status === statusFilter);
    }

    if (directionFilter !== "all") {
      list = list.filter((c) => c.direction === directionFilter);
    }

    if (dateRange.from) {
      const fromTs = dateRange.from.getTime();
      list = list.filter((c) => c.timestamp.getTime() >= fromTs);
    }
    if (dateRange.to) {
      const toTs = new Date(dateRange.to);
      toTs.setHours(23, 59, 59, 999);
      list = list.filter((c) => c.timestamp.getTime() <= toTs.getTime());
    }

    return list.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
  }, [search, statusFilter, directionFilter, dateRange]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const hasActiveFilters =
    search || statusFilter !== "all" || directionFilter !== "all" || dateRange.from;

  const clearFilters = () => {
    setSearch("");
    setStatusFilter("all");
    setDirectionFilter("all");
    setDateRange({ from: undefined, to: undefined });
    setPage(0);
  };

  return (
    <div className="container mx-auto space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Calls</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Monitor and search through all Acefone calls
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by SID, from, or to..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                className="pl-9 text-sm"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <Select
              value={statusFilter}
              onValueChange={(v) => {
                setStatusFilter(v);
                setPage(0);
              }}
            >
              <SelectTrigger className="w-[130px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="answered">Answered</SelectItem>
                <SelectItem value="missed">Missed</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="active">Active</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={directionFilter}
              onValueChange={(v) => {
                setDirectionFilter(v);
                setPage(0);
              }}
            >
              <SelectTrigger className="w-[130px]">
                <SelectValue placeholder="Direction" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="inbound">Inbound</SelectItem>
                <SelectItem value="outbound">Outbound</SelectItem>
              </SelectContent>
            </Select>

            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className={cn(
                    "w-[220px] justify-start text-left text-xs font-normal",
                    !dateRange.from && "text-muted-foreground",
                  )}
                >
                  <Filter className="mr-1.5 h-3.5 w-3.5 shrink-0" />
                  {dateRange.from
                    ? `${format(dateRange.from, "MMM dd")}${dateRange.to ? ` - ${format(dateRange.to, "MMM dd")}` : " - ..."}`
                    : "Date range"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="end">
                <Calendar
                  mode="range"
                  selected={dateRange as { from: Date; to?: Date }}
                  onSelect={(range) => {
                    setDateRange({
                      from: range?.from,
                      to: range?.to,
                    });
                    setPage(0);
                  }}
                  numberOfMonths={2}
                />
              </PopoverContent>
            </Popover>

            {hasActiveFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearFilters}
                className="gap-1 text-xs text-muted-foreground"
              >
                <X className="h-3.5 w-3.5" />
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold">
              {loading ? (
                <Skeleton className="h-5 w-24" />
              ) : (
                <>
                  {filtered.length} call{filtered.length !== 1 ? "s" : ""}
                </>
              )}
            </CardTitle>
            {!loading && filtered.length > PAGE_SIZE && (
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page === 0}
                  onClick={() => setPage(0)}
                  aria-label="First page"
                >
                  <ChevronsLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <span className="min-w-[60px] text-center text-xs tabular-nums text-muted-foreground">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(totalPages - 1)}
                  aria-label="Last page"
                >
                  <ChevronsRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>

        {loading ? (
          <CardContent className="space-y-3">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        ) : paged.length === 0 ? (
          <CardContent>
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-4 rounded-full border bg-muted/50 p-3">
                <Phone className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-muted-foreground">
                No calls found
              </p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                {hasActiveFilters
                  ? "Try adjusting your filters"
                  : "Calls will appear here once calls are made"}
              </p>
              {hasActiveFilters && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={clearFilters}
                  className="mt-4"
                >
                  Clear filters
                </Button>
              )}
            </div>
          </CardContent>
        ) : (
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="h-9 px-4 text-[11px]">Date</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">Call SID</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">From</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">To</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">Dir.</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">Duration</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">Status</TableHead>
                  <TableHead className="h-9 px-4 text-[11px]">Cost</TableHead>
                  <TableHead className="h-9 w-10 px-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {paged.map((call) => (
                  <TableRow
                    key={call.id}
                    className="cursor-pointer transition-colors hover:bg-muted/30"
                    tabIndex={0}
                    role="link"
                    onClick={() => router.push(`/calls/${call.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") router.push(`/calls/${call.id}`);
                    }}
                  >
                    <TableCell className="px-4 py-2.5 text-xs tabular-nums text-muted-foreground">
                      {format(call.timestamp, "MMM dd, HH:mm")}
                    </TableCell>
                    <TableCell className="px-4 py-2.5">
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                        {call.callSid.slice(0, 10)}...
                      </code>
                    </TableCell>
                    <TableCell className="px-4 py-2.5 font-mono text-xs">
                      {call.from}
                    </TableCell>
                    <TableCell className="px-4 py-2.5 font-mono text-xs">
                      {call.to}
                    </TableCell>
                    <TableCell className="px-4 py-2.5">
                      {call.direction === "inbound" ? (
                        <span className="inline-flex items-center gap-1 text-xs text-blue-500">
                          <PhoneIncoming className="h-3 w-3" />
                          In
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-violet-500">
                          <PhoneOutgoing className="h-3 w-3" />
                          Out
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="px-4 py-2.5 font-mono text-xs tabular-nums">
                      {call.status === "active" ? (
                        <span className="text-blue-500">Live</span>
                      ) : (
                        formatDuration(call.duration)
                      )}
                    </TableCell>
                    <TableCell className="px-4 py-2.5">
                      {statusBadge(call.status)}
                    </TableCell>
                    <TableCell className="px-4 py-2.5 font-mono text-xs tabular-nums text-muted-foreground">
                      {formatCost(call.cost)}
                    </TableCell>
                    <TableCell className="px-4 py-2.5">
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
