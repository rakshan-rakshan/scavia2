"use client";

import { format } from "date-fns";
import {
  Activity,
  ChevronRight,
  Clock,
  DollarSign,
  Phone,
  PhoneCall,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

// ─── Types ───────────────────────────────────────────────────────────

type CallStatus = "answered" | "missed" | "failed" | "active";

type StreamStatus = "streaming" | "paused" | "disconnected";

interface CallRecord {
  id: string;
  callSid: string;
  from: string;
  to: string;
  direction: "inbound" | "outbound";
  duration: number;
  status: CallStatus;
  cost: number;
  timestamp: Date;
}

interface ActiveStream {
  callSid: string;
  from: string;
  to: string;
  startedAt: Date;
  status: StreamStatus;
  audioLevel: number;
}

interface VolumeDataPoint {
  hour: string;
  calls: number;
}

interface DashboardMetrics {
  activeCalls: number;
  totalCallsToday: number;
  avgHandleTime: number;
  totalCostToday: number;
  activeCallsTrend: number;
  totalCallsTrend: number;
  avgHandleTimeTrend: number;
  totalCostTrend: number;
}

// ─── Mock Data ───────────────────────────────────────────────────────

const MOCK_METRICS: DashboardMetrics = {
  activeCalls: 3,
  totalCallsToday: 142,
  avgHandleTime: 184,
  totalCostToday: 47.83,
  activeCallsTrend: 12.5,
  totalCallsTrend: -3.2,
  avgHandleTimeTrend: -5.1,
  totalCostTrend: 8.7,
};

const MOCK_VOLUME_DATA: VolumeDataPoint[] = Array.from({ length: 24 }, (_, i) => ({
  hour: `${i.toString().padStart(2, "0")}:00`,
  calls: Math.floor(Math.random() * 40) + 5,
}));

const MOCK_ACTIVE_STREAMS: ActiveStream[] = [
  {
    callSid: "CA8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d",
    from: "+14155551234",
    to: "+918765432109",
    startedAt: new Date(Date.now() - 1000 * 60 * 3),
    status: "streaming",
    audioLevel: 0.72,
  },
  {
    callSid: "CA9b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    from: "+12125559876",
    to: "+919876543210",
    startedAt: new Date(Date.now() - 1000 * 60 * 7),
    status: "streaming",
    audioLevel: 0.45,
  },
  {
    callSid: "CA0c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
    from: "+13105550123",
    to: "+917654321098",
    startedAt: new Date(Date.now() - 1000 * 60 * 12),
    status: "paused",
    audioLevel: 0.0,
  },
];

const MOCK_RECENT_CALLS: CallRecord[] = Array.from({ length: 20 }, (_, i) => {
  const statuses: CallStatus[] = ["answered", "missed", "failed", "active"];
  const dirs: ("inbound" | "outbound")[] = ["inbound", "outbound"];
  const froms = [
    "+14155551234",
    "+12125559876",
    "+13105550123",
    "+16175551234",
    "+17205550123",
  ];
  const tos = [
    "+918765432109",
    "+919876543210",
    "+917654321098",
    "+916543210987",
    "+915432109876",
  ];
  return {
    id: `call-${i}`,
    callSid: `CA${Math.random().toString(16).slice(2, 34)}`,
    from: froms[i % froms.length],
    to: tos[i % tos.length],
    direction: dirs[i % 2],
    duration: Math.floor(Math.random() * 600) + 10,
    status: i === 0 ? "active" : statuses[i % 4],
    cost: Math.random() * 0.5 + 0.01,
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * (i * 2 + 1)),
  };
});

// ─── Helpers ─────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

function truncateSid(sid: string): string {
  return sid.slice(0, 8) + "...";
}

function liveTimer(startedAt: Date): string {
  const diff = Math.floor((Date.now() - startedAt.getTime()) / 1000);
  return formatDuration(diff);
}

function statusColor(status: CallStatus): string {
  switch (status) {
    case "answered":
      return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20";
    case "missed":
      return "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20";
    case "failed":
      return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20";
    case "active":
      return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20";
  }
}

function streamStatusBadge(status: StreamStatus) {
  switch (status) {
    case "streaming":
      return (
        <Badge
          variant="success"
          className="gap-1.5 px-2 py-0.5 text-[11px]"
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          Streaming
        </Badge>
      );
    case "paused":
      return (
        <Badge variant="secondary" className="gap-1.5 px-2 py-0.5 text-[11px]">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Paused
        </Badge>
      );
    case "disconnected":
      return (
        <Badge
          variant="outline"
          className="gap-1.5 px-2 py-0.5 text-[11px] text-muted-foreground"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
          Disconnected
        </Badge>
      );
  }
}

// ─── Animated Counter ────────────────────────────────────────────────

function AnimatedCounter({
  value,
  suffix = "",
  prefix = "",
  decimals = 0,
}: {
  value: number;
  suffix?: string;
  prefix?: string;
  decimals?: number;
}) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<number | null>(null);

  useEffect(() => {
    const start = performance.now();
    const from = 0;
    const to = value;
    const duration = 800;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from + (to - from) * eased);
      if (progress < 1) ref.current = requestAnimationFrame(tick);
    }

    ref.current = requestAnimationFrame(tick);
    return () => {
      if (ref.current) cancelAnimationFrame(ref.current);
    };
  }, [value]);

  return (
    <span>
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

// ─── Stat Card ───────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  trend,
  icon: Icon,
  loading,
}: {
  title: string;
  value: number;
  trend: number;
  icon: typeof Phone;
  loading: boolean;
}) {
  const isUp = trend >= 0;
  const formatted =
    title === "Total Cost Today"
      ? value
      : title === "Average Handle Time"
        ? value
        : value;

  return (
    <Card className="group relative overflow-hidden transition-all duration-200 hover:shadow-md">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
          {title}
        </CardTitle>
        <div className="rounded-lg border bg-muted/50 p-1.5 text-muted-foreground transition-colors group-hover:border-muted-foreground/20">
          <Icon className="h-4 w-4" />
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-4 w-16" />
          </div>
        ) : (
          <>
            <div className="text-2xl font-bold tracking-tight">
              {title === "Total Cost Today" && "$"}
              <AnimatedCounter
                value={formatted}
                suffix={
                  title === "Average Handle Time" ? "s" : ""
                }
                decimals={title === "Total Cost Today" ? 2 : 0}
              />
            </div>
            <div className="mt-1 flex items-center gap-1.5">
              <div
                className={cn(
                  "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium leading-none",
                  isUp
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "bg-red-500/10 text-red-600 dark:text-red-400",
                )}
              >
                <span className="text-[10px]">{isUp ? "↑" : "↓"}</span>
                {Math.abs(trend).toFixed(1)}%
              </div>
              <span className="text-[11px] text-muted-foreground">vs yesterday</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Call Volume Chart ───────────────────────────────────────────────

function CallVolumeChart({
  data,
  loading,
}: {
  data: VolumeDataPoint[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-3 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[280px] w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-sm font-semibold">Call Volume (24h)</CardTitle>
        <p className="text-xs text-muted-foreground">
          Total calls per hour across all Acefone streams
        </p>
      </CardHeader>
      <CardContent>
        <div className="h-[280px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <defs>
                <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--color-border)"
                vertical={false}
              />
              <XAxis
                dataKey="hour"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
                interval={3}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
                width={32}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--color-popover)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-lg)",
                  boxShadow: "var(--shadow-md)",
                  fontSize: 12,
                }}
                labelStyle={{ fontWeight: 600, marginBottom: 4 }}
                formatter={(value: number) => [`${value} calls`, "Volume"]}
              />
              <Area
                type="monotone"
                dataKey="calls"
                stroke="var(--color-chart-1)"
                strokeWidth={2}
                fill="url(#volumeGradient)"
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Active Streams Panel ────────────────────────────────────────────

function AudioLevelBar({ level }: { level: number }) {
  const bars = 8;
  const activeBars = Math.round(level * bars);
  return (
    <div className="flex items-end gap-[2px] h-4">
      {Array.from({ length: bars }, (_, i) => (
        <div
          key={i}
          className={cn(
            "w-[3px] rounded-full transition-all duration-150",
            i < activeBars
              ? "bg-emerald-500"
              : "bg-muted-foreground/20",
          )}
          style={{
            height: `${((i + 1) / bars) * 100}%`,
            opacity: i < activeBars ? 0.4 + (i / bars) * 0.6 : 0.3,
          }}
        />
      ))}
    </div>
  );
}

function ActiveStreamsPanel({
  streams,
  loading,
}: {
  streams: ActiveStream[];
  loading: boolean;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (loading || streams.length === 0) return;
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, [loading, streams.length]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3 w-52" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (streams.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Active Streams</CardTitle>
          <p className="text-xs text-muted-foreground">
            Currently active Acefone media streams
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 rounded-full border bg-muted/50 p-3">
              <PhoneCall className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-muted-foreground">
              No active streams
            </p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              Active calls will appear here in real-time
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold">Active Streams</CardTitle>
            <p className="text-xs text-muted-foreground">
              Currently active Acefone media streams
            </p>
          </div>
          <Badge variant="secondary" className="gap-1 px-2 py-0.5 text-[11px]">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            {streams.length} active
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y">
          {streams.map((stream) => (
            <div
              key={stream.callSid}
              className="flex items-center gap-4 px-6 py-3 transition-colors hover:bg-muted/30"
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <div className="hidden sm:block">
                  <AudioLevelBar level={stream.audioLevel} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
                      {truncateSid(stream.callSid)}
                    </code>
                    {streamStatusBadge(stream.status)}
                  </div>
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {stream.from} → {stream.to}
                  </p>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-xs tabular-nums text-foreground">
                  {liveTimer(stream.startedAt)}
                </p>
                <p className="text-[10px] text-muted-foreground">duration</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Recent Calls Table ──────────────────────────────────────────────

function RecentCallsTable({
  calls,
  loading,
}: {
  calls: CallRecord[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-3 w-48" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  if (calls.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Recent Calls</CardTitle>
          <p className="text-xs text-muted-foreground">Last 20 Acefone calls</p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 rounded-full border bg-muted/50 p-3">
              <Phone className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-muted-foreground">
              No calls yet
            </p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              Call history will appear here once calls start flowing
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-semibold">Recent Calls</CardTitle>
            <p className="text-xs text-muted-foreground">Last 20 Acefone calls</p>
          </div>
          <Button variant="ghost" size="sm" asChild className="gap-1.5 text-xs">
            <Link href="/calls">
              View all
              <ChevronRight className="h-3 w-3" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="h-9 px-4 text-[11px]">Time</TableHead>
              <TableHead className="h-9 px-4 text-[11px]">From</TableHead>
              <TableHead className="h-9 px-4 text-[11px]">To</TableHead>
              <TableHead className="h-9 px-4 text-[11px]">Dur.</TableHead>
              <TableHead className="h-9 px-4 text-[11px]">Status</TableHead>
              <TableHead className="h-9 px-4 text-[11px]">Cost</TableHead>
              <TableHead className="h-9 w-10 px-4" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {calls.map((call) => (
              <TableRow
                key={call.id}
                className="cursor-pointer transition-colors hover:bg-muted/30"
                tabIndex={0}
                role="link"
                onClick={() => window.open(`/calls/${call.id}`, "_self")}
                onKeyDown={(e) => {
                  if (e.key === "Enter") window.open(`/calls/${call.id}`, "_self");
                }}
              >
                <TableCell className="px-4 py-2.5 text-xs tabular-nums text-muted-foreground">
                  {format(call.timestamp, "HH:mm")}
                </TableCell>
                <TableCell className="px-4 py-2.5 font-mono text-xs">
                  {call.from}
                </TableCell>
                <TableCell className="px-4 py-2.5 font-mono text-xs">
                  {call.to}
                </TableCell>
                <TableCell className="px-4 py-2.5 text-xs tabular-nums">
                  {call.status === "active" ? (
                    <span className="text-blue-500">Live</span>
                  ) : (
                    formatDuration(call.duration)
                  )}
                </TableCell>
                <TableCell className="px-4 py-2.5">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none",
                      statusColor(call.status),
                    )}
                  >
                    {call.status === "active" && (
                      <span className="relative mr-1 flex h-1.5 w-1.5">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
                      </span>
                    )}
                    {call.status.charAt(0).toUpperCase() + call.status.slice(1)}
                  </span>
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
    </Card>
  );
}

// ─── Page ────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [volumeData, setVolumeData] = useState<VolumeDataPoint[]>([]);
  const [activeStreams, setActiveStreams] = useState<ActiveStream[]>([]);
  const [recentCalls, setRecentCalls] = useState<CallRecord[]>([]);

  const fetchData = useCallback(() => {
    setLoading(true);
    // Simulate API fetch
    setTimeout(() => {
      setMetrics(MOCK_METRICS);
      setVolumeData(MOCK_VOLUME_DATA);
      setActiveStreams(MOCK_ACTIVE_STREAMS);
      setRecentCalls(MOCK_RECENT_CALLS);
      setLoading(false);
    }, 600);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  return (
    <div className="container mx-auto space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Real-time Acefone call monitoring
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={cn(
              "gap-1.5 text-xs transition-colors",
              autoRefresh && "border-emerald-500/50 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
            )}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", autoRefresh && "animate-spin-slow")} />
            {autoRefresh ? "Auto-refresh on" : "Auto-refresh"}
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Active Calls"
          value={metrics?.activeCalls ?? 0}
          trend={metrics?.activeCallsTrend ?? 0}
          icon={Activity}
          loading={loading}
        />
        <StatCard
          title="Total Calls Today"
          value={metrics?.totalCallsToday ?? 0}
          trend={metrics?.totalCallsTrend ?? 0}
          icon={PhoneCall}
          loading={loading}
        />
        <StatCard
          title="Average Handle Time"
          value={metrics?.avgHandleTime ?? 0}
          trend={metrics?.avgHandleTimeTrend ?? 0}
          icon={Clock}
          loading={loading}
        />
        <StatCard
          title="Total Cost Today"
          value={metrics?.totalCostToday ?? 0}
          trend={metrics?.totalCostTrend ?? 0}
          icon={DollarSign}
          loading={loading}
        />
      </div>

      {/* Chart & Active Streams */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <CallVolumeChart data={volumeData} loading={loading} />
        </div>
        <div className="lg:col-span-2">
          <ActiveStreamsPanel streams={activeStreams} loading={loading} />
        </div>
      </div>

      {/* Recent Calls */}
      <RecentCallsTable calls={recentCalls} loading={loading} />
    </div>
  );
}
