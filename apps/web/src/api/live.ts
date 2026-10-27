// Live status (P2.6): one GET /v1/events stream per signed-in tab. Each status change refreshes the queries it can
// change (the lists, that recording, the overview, the review queues), so pages update without a reload.
//
// The stream is read with fetch, not EventSource, because it needs the Authorization header. When the server ends
// a stream (every few minutes, on purpose) the tab reconnects at once with Last-Event-ID, so nothing is missed;
// after an error it waits 1, 2, 4 ... up to 30 s. While there is no live stream (503 live_unavailable, or between
// attempts) `isLive()` is false and the hooks poll every REFRESH_MS instead (api/hooks.ts).

import type { QueryClient, QueryKey } from "@tanstack/react-query";

export interface LiveEvent {
  id: string | null;
  type: string;
  recording_id: string | null;
  status: string | null;
  reason: string | null;
  at: string;
}

// --- Whether the live stream is up (read by the hooks' refetchInterval, and by components via useSyncExternalStore)

let live = false;
const listeners = new Set<() => void>();

export function isLive(): boolean {
  return live;
}

export function subscribeLive(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setLive(next: boolean): void {
  if (next === live) return;
  live = next;
  listeners.forEach((listener) => listener());
}

// --- Parsing the text/event-stream format

/** Splits buffered text into complete events (blank-line separated) and the unfinished rest. Comments are skipped. */
export function parseEvents(buffer: string): { events: LiveEvent[]; rest: string; connected: boolean } {
  const normalised = buffer.replace(/\r\n/g, "\n");
  const blocks = normalised.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: LiveEvent[] = [];
  let connected = false;
  for (const block of blocks) {
    let id: string | null = null;
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line === ": connected") connected = true;
      else if (line.startsWith("id: ")) id = line.slice(4);
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (data.length === 0) continue;
    try {
      events.push({ ...(JSON.parse(data.join("\n")) as Omit<LiveEvent, "id">), id });
    } catch {
      // a malformed event is skipped; the next refresh shows the truth anyway
    }
  }
  return { events, rest, connected };
}

/** The cached queries an event can change. Prefix keys: ["recording", id] also matches ["recording", id, token]. */
export function affectedQueries(event: LiveEvent): QueryKey[] {
  const keys: QueryKey[] = [["recordings"], ["overview"]];
  if (event.recording_id) {
    keys.push(["recording", event.recording_id], ["analysis", event.recording_id]);
    keys.push(["analysis-history", event.recording_id]);
  }
  if (event.status === "NEEDS_REVIEW" || event.type === "recording.transcribing") keys.push(["reviews"]);
  if (event.status === "COMPLETED") keys.push(["people-summary"], ["people"]);
  // A recording's length is measured by preprocessing, so this month's hours change when diarization starts.
  if (event.status === "DIARIZING") keys.push(["usage"]);
  if (event.type === "dispute.resolved") keys.push(["disputes"]);
  return keys;
}

// --- The connection

export const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000];
export const UNAVAILABLE_RETRY_MS = 60_000;

export interface LiveOptions {
  token: string;
  queryClient: QueryClient;
  fetchImpl?: typeof fetch;
  /** Waits before the next attempt; injectable for tests. */
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

function defaultSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/** Keeps a live stream open until the returned function is called. */
export function connectLive({ token, queryClient, fetchImpl = fetch, sleep = defaultSleep }: LiveOptions): () => void {
  const controller = new AbortController();
  const { signal } = controller;
  let lastEventId: string | null = null;

  async function once(): Promise<"ended" | "unavailable" | "unauthorised" | "failed"> {
    const headers: Record<string, string> = { Accept: "text/event-stream", Authorization: `Bearer ${token}` };
    if (lastEventId) headers["Last-Event-ID"] = lastEventId;
    const response = await fetchImpl("/v1/events", { headers, signal });
    if (response.status === 401) return "unauthorised";
    if (response.status === 503) return "unavailable";
    const isStream = (response.headers.get("content-type") ?? "").startsWith("text/event-stream");
    if (!response.ok || !response.body || !isStream) return "failed";
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let opened = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return opened ? "ended" : "failed"; // a stream that never said "connected" is not retried at once
      const parsed = parseEvents(buffer + value);
      buffer = parsed.rest;
      if (parsed.connected) {
        opened = true;
        setLive(true);
      }
      for (const event of parsed.events) {
        if (event.id) lastEventId = event.id;
        for (const key of affectedQueries(event)) void queryClient.invalidateQueries({ queryKey: key });
      }
    }
  }

  void (async () => {
    let failures = 0;
    while (!signal.aborted) {
      let outcome: Awaited<ReturnType<typeof once>>;
      try {
        outcome = await once();
      } catch {
        outcome = "failed";
      }
      if (signal.aborted) break;
      if (outcome === "ended") {
        failures = 0;
        continue; // the server closes streams on purpose; reconnect at once with Last-Event-ID
      }
      setLive(false);
      if (outcome === "unauthorised") break; // the session handles signing out
      const wait =
        outcome === "unavailable" ? UNAVAILABLE_RETRY_MS : BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)];
      failures += 1;
      await sleep(wait ?? UNAVAILABLE_RETRY_MS, signal);
    }
    setLive(false);
  })();

  return () => controller.abort();
}
