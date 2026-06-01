"use client";

import { format } from "date-fns";
import {
  AlertTriangle,
  ChevronLeft,
  Download,
  GripVertical,
  Mic,
  MicOff,
  Pause,
  PhoneIncoming,
  PhoneOff,
  PhoneOutgoing,
  Play,
  Radio,
  StopCircle,
  Volume2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// ─── Types ───────────────────────────────────────────────────────────

type CallStatus = "answered" | "missed" | "failed" | "active";

interface CallDetail {
  id: string;
  callSid: string;
  from: string;
  to: string;
  direction: "inbound" | "outbound";
  duration: number;
  status: CallStatus;
  cost: number;
  startedAt: Date;
  endedAt: Date | null;
  hasRecording: boolean;
  recordingUrl: string | null;
}

interface TimelineEvent {
  id: string;
  timestamp: Date;
  type: "connected" | "media_start" | "dtmf" | "transfer" | "hangup" | "bargein";
  label: string;
  detail?: string;
}

interface TranscriptLine {
  id: string;
  timestamp: Date;
  speaker: "user" | "bot";
  text: string;
}

interface QualityMetric {
  label: string;
  value: string;
  status: "good" | "warning" | "critical";
}

interface DtmfEntry {
  key: string;
  timestamp: Date;
}

// ─── Mock Data ───────────────────────────────────────────────────────

const MOCK_CALL: CallDetail = {
  id: "call-3",
  callSid: "CA8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d",
  from: "+14155551234",
  to: "+918765432109",
  direction: "outbound",
  duration: 347,
  status: "answered",
  cost: 0.0847,
  startedAt: new Date(Date.now() - 1000 * 60 * 60 * 2),
  endedAt: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 347),
  hasRecording: true,
  recordingUrl: "#",
};

const MOCK_TIMELINE: TimelineEvent[] = [
  {
    id: "ev-1",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2),
    type: "connected",
    label: "Call connected",
    detail: "SIP INVITE accepted",
  },
  {
    id: "ev-2",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 2),
    type: "media_start",
    label: "Media stream started",
    detail: "Acefone WebRTC stream established",
  },
  {
    id: "ev-3",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 15),
    type: "dtmf",
    label: "DTMF received",
    detail: "Key: 1",
  },
  {
    id: "ev-4",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 30),
    type: "dtmf",
    label: "DTMF received",
    detail: "Key: 2",
  },
  {
    id: "ev-5",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 180),
    type: "transfer",
    label: "Call transferred",
    detail: "Transferred to +918765432109",
  },
  {
    id: "ev-6",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 347),
    type: "hangup",
    label: "Call ended",
    detail: "Disconnected by caller",
  },
];

const MOCK_TRANSCRIPT: TranscriptLine[] = [
  {
    id: "tr-1",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 3),
    speaker: "bot",
    text: "Hello, this is Alex from Acefone customer support. How can I help you today?",
  },
  {
    id: "tr-2",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 8),
    speaker: "user",
    text: "Hi, I'm having trouble with my account. I can't log in.",
  },
  {
    id: "tr-3",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 14),
    speaker: "bot",
    text: "I'm sorry to hear that. Let me look into your account. Could you please provide me with your registered email address or phone number?",
  },
  {
    id: "tr-4",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 20),
    speaker: "user",
    text: "Yes, it's john.doe@example.com.",
  },
  {
    id: "tr-5",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 28),
    speaker: "bot",
    text: "Thank you. I can see your account here. It appears your account was temporarily locked due to multiple failed login attempts. Let me unlock that for you.",
  },
  {
    id: "tr-6",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 42),
    speaker: "bot",
    text: "I've unlocked your account. Please try logging in again. You may need to reset your password.",
  },
  {
    id: "tr-7",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 48),
    speaker: "user",
    text: "Okay, thank you. I'll try that. Is there anything else I need to do?",
  },
  {
    id: "tr-8",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 56),
    speaker: "bot",
    text: "No, that should be all. I'll also send you a confirmation email with instructions. Is there anything else I can help you with?",
  },
  {
    id: "tr-9",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 63),
    speaker: "user",
    text: "No, that's all. Thank you for your help!",
  },
  {
    id: "tr-10",
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 68),
    speaker: "bot",
    text: "You're welcome! Have a great day. Goodbye!",
  },
];

const MOCK_QUALITY: QualityMetric[] = [
  { label: "Latency", value: "45ms", status: "good" },
  { label: "Packet Loss", value: "0.2%", status: "good" },
  { label: "Jitter", value: "8ms", status: "good" },
];

const MOCK_DTMF: DtmfEntry[] = [
  { key: "1", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 15) },
  { key: "2", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2 + 1000 * 30) },
];

// ─── Helpers ─────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
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
      {s.label}
    </span>
  );
}

// ─── Timeline Event Icon ─────────────────────────────────────────────

function TimelineIcon({ type }: { type: TimelineEvent["type"] }) {
  const iconClass = "h-3.5 w-3.5";
  switch (type) {
    case "connected":
      return <PhoneIncoming className={cn(iconClass, "text-emerald-500")} />;
    case "media_start":
      return <Radio className={cn(iconClass, "text-blue-500")} />;
    case "dtmf":
      return <Volume2 className={cn(iconClass, "text-amber-500")} />;
    case "transfer":
      return <PhoneOutgoing className={cn(iconClass, "text-violet-500")} />;
    case "hangup":
      return <PhoneOff className={cn(iconClass, "text-red-500")} />;
    case "bargein":
      return <AlertTriangle className={cn(iconClass, "text-amber-500")} />;
  }
}

// ─── Quality Badge ───────────────────────────────────────────────────

function QualityDot({ status }: { status: QualityMetric["status"] }) {
  const colors = {
    good: "bg-emerald-500",
    warning: "bg-amber-500",
    critical: "bg-red-500",
  };
  return <span className={cn("h-1.5 w-1.5 rounded-full", colors[status])} />;
}

// ─── Split Pane Drag Handle ──────────────────────────────────────────

function SplitPane({
  left,
  right,
  defaultLeftPercent = 55,
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  defaultLeftPercent?: number;
}) {
  const [leftPercent, setLeftPercent] = useState(defaultLeftPercent);
  const dragging = useRef(false);

  const handleMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const container = document.getElementById("split-pane-container");
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftPercent(Math.min(Math.max(pct, 30), 70));
    };

    const handleMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  return (
    <div
      id="split-pane-container"
      className="flex flex-1 overflow-hidden"
      style={{ minHeight: 0 }}
    >
      <div className="overflow-y-auto" style={{ width: `${leftPercent}%` }}>
        {left}
      </div>
      <div
        className="flex w-1.5 shrink-0 cursor-col-resize items-center justify-center bg-border/30 transition-colors hover:bg-border/60 active:bg-border"
        onMouseDown={handleMouseDown}
        role="separator"
        tabIndex={0}
        aria-label="Resize pane"
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setLeftPercent((p) => Math.max(30, p - 2));
          if (e.key === "ArrowRight") setLeftPercent((p) => Math.min(70, p + 2));
        }}
      >
        <GripVertical className="h-4 w-3 text-muted-foreground/40" />
      </div>
      <div className="overflow-y-auto" style={{ width: `${100 - leftPercent}%` }}>
        {right}
      </div>
    </div>
  );
}

// ─── Loading State ───────────────────────────────────────────────────

function DetailSkeleton() {
  return (
    <div className="container mx-auto space-y-6 p-6">
      <div className="flex items-center gap-3">
        <Skeleton className="h-8 w-8" />
        <Skeleton className="h-6 w-48" />
      </div>
      <div className="flex gap-6">
        <div className="flex-1 space-y-4">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
        <div className="w-80 shrink-0 space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────

export default function CallDetailPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  // Simulate loading
  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 500);
    return () => clearTimeout(timer);
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  if (loading) return <DetailSkeleton />;

  return (
    <div className="container mx-auto flex h-full flex-col p-6">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={() => router.push("/calls")}
          aria-label="Back to calls"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-semibold">
              Call {MOCK_CALL.callSid.slice(0, 14)}...
            </h1>
            {statusBadge(MOCK_CALL.status)}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {format(MOCK_CALL.startedAt, "MMM dd, yyyy HH:mm:ss")} &middot;{" "}
            {MOCK_CALL.direction === "inbound" ? "Inbound" : "Outbound"}
          </p>
        </div>
      </div>

      {/* Split Pane */}
      <SplitPane
        left={
          <div className="space-y-4 pr-3">
            {/* Timeline */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Event Timeline</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative pl-6">
                  {/* Vertical line */}
                  <div className="absolute left-[11px] top-1.5 h-[calc(100%-12px)] w-px bg-border" />
                  <div className="space-y-4">
                    {MOCK_TIMELINE.map((event) => (
                      <div key={event.id} className="relative">
                        <div className="absolute -left-[22px] flex h-5 w-5 items-center justify-center rounded-full border bg-background">
                          <TimelineIcon type={event.type} />
                        </div>
                        <div>
                          <p className="text-xs font-medium text-foreground">
                            {event.label}
                          </p>
                          {event.detail && (
                            <p className="text-[11px] text-muted-foreground">
                              {event.detail}
                            </p>
                          )}
                          <p className="mt-0.5 text-[10px] tabular-nums text-muted-foreground/60">
                            {format(event.timestamp, "HH:mm:ss")}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Transcript */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Transcript</CardTitle>
              </CardHeader>
              <CardContent className="max-h-[400px] space-y-3 overflow-y-auto">
                {MOCK_TRANSCRIPT.map((line) => (
                  <div
                    key={line.id}
                    className={cn(
                      "rounded-lg border px-3 py-2",
                      line.speaker === "bot"
                        ? "border-emerald-500/20 bg-emerald-500/5"
                        : "border-blue-500/20 bg-blue-500/5",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "text-[10px] font-medium uppercase tracking-wider",
                          line.speaker === "bot"
                            ? "text-emerald-500"
                            : "text-blue-500",
                        )}
                      >
                        {line.speaker === "bot" ? "Agent" : "Customer"}
                      </span>
                      <span className="text-[10px] tabular-nums text-muted-foreground/50">
                        {format(line.timestamp, "HH:mm:ss")}
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm leading-relaxed text-foreground">
                      {line.text}
                    </p>
                  </div>
                ))}
                <div ref={transcriptEndRef} />
              </CardContent>
            </Card>
          </div>
        }
        right={
          <div className="space-y-4 pl-3">
            {/* Call Metadata */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Call Info</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2.5">
                <InfoRow label="Call SID" mono>
                  {MOCK_CALL.callSid.slice(0, 20)}...
                </InfoRow>
                <InfoRow label="From">{MOCK_CALL.from}</InfoRow>
                <InfoRow label="To">{MOCK_CALL.to}</InfoRow>
                <InfoRow label="Direction">
                  {MOCK_CALL.direction === "inbound" ? "Inbound" : "Outbound"}
                </InfoRow>
                <Separator />
                <InfoRow label="Duration" mono>
                  {formatDuration(MOCK_CALL.duration)}
                </InfoRow>
                <InfoRow label="Cost" mono>
                  {formatCost(MOCK_CALL.cost)}
                </InfoRow>
                <InfoRow label="Started" mono>
                  {format(MOCK_CALL.startedAt, "HH:mm:ss")}
                </InfoRow>
                <InfoRow label="Ended" mono>
                  {MOCK_CALL.endedAt
                    ? format(MOCK_CALL.endedAt, "HH:mm:ss")
                    : "—"}
                </InfoRow>
              </CardContent>
            </Card>

            {/* Audio Controls */}
            {MOCK_CALL.hasRecording && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Recording</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsPlaying(!isPlaying)}
                      className="gap-1.5 text-xs"
                      aria-label={isPlaying ? "Pause recording" : "Play recording"}
                    >
                      {isPlaying ? (
                        <Pause className="h-3.5 w-3.5" />
                      ) : (
                        <Play className="h-3.5 w-3.5" />
                      )}
                      {isPlaying ? "Pause" : "Play"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1.5 text-xs"
                      aria-label="Download recording"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download
                    </Button>
                  </div>
                  {/* Waveform placeholder */}
                  <div className="mt-3 flex h-12 items-center justify-center rounded-lg border bg-muted/30">
                    <div className="flex items-center gap-0.5">
                      {Array.from({ length: 32 }, (_, i) => (
                        <div
                          key={i}
                          className="w-[2px] rounded-full bg-muted-foreground/20"
                          style={{
                            height: `${Math.sin(i * 0.8) * 12 + 16}px`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Stream Controls */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">
                  Stream Controls
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2 text-xs"
                  onClick={() => setIsMuted(!isMuted)}
                  aria-label={isMuted ? "Unmute user" : "Mute user"}
                >
                  {isMuted ? (
                    <MicOff className="h-3.5 w-3.5 text-red-500" />
                  ) : (
                    <Mic className="h-3.5 w-3.5" />
                  )}
                  {isMuted ? "Unmute User" : "Mute User"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2 text-xs"
                  aria-label="Send barge-in"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                  Barge-in (Send Clear)
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  className="w-full justify-start gap-2 text-xs"
                  aria-label="Force hangup"
                >
                  <StopCircle className="h-3.5 w-3.5" />
                  Force Hangup
                </Button>
              </CardContent>
            </Card>

            {/* Quality Metrics */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">
                  Quality Metrics
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {MOCK_QUALITY.map((metric) => (
                  <div
                    key={metric.label}
                    className="flex items-center justify-between"
                  >
                    <span className="text-xs text-muted-foreground">
                      {metric.label}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
                      <QualityDot status={metric.status} />
                      {metric.value}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* DTMF Log */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">DTMF Log</CardTitle>
              </CardHeader>
              <CardContent>
                {MOCK_DTMF.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No DTMF keys pressed during this call
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {MOCK_DTMF.map((entry, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between rounded-md border bg-muted/20 px-3 py-1.5"
                      >
                        <span className="font-mono text-xs font-bold text-foreground">
                          {entry.key}
                        </span>
                        <span className="text-[10px] tabular-nums text-muted-foreground">
                          {format(entry.timestamp, "HH:mm:ss")}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        }
      />
    </div>
  );
}

function InfoRow({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-xs font-medium",
          mono && "font-mono tabular-nums",
        )}
      >
        {children}
      </span>
    </div>
  );
}
