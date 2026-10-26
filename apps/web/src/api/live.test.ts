import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { affectedQueries, BACKOFF_MS, connectLive, isLive, parseEvents, UNAVAILABLE_RETRY_MS } from "./live";

const EVENT = (id: string, status: string, rid = "r1") =>
  `id: ${id}\nevent: status\ndata: ${JSON.stringify({ type: `recording.${status.toLowerCase()}`, recording_id: rid, status, reason: "x", at: "2026-10-26T05:00:00Z" })}\n\n`;

function streamResponse(chunks: string[], status = 200): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

let stop: (() => void) | undefined;
afterEach(() => stop?.());

describe("parseEvents", () => {
  it("returns complete events and keeps the unfinished rest", () => {
    const text = ": connected\n\n" + EVENT("e1", "ANALYZING") + ': ping\n\nid: e2\nevent: status\ndata: {"ty';
    const { events, rest, connected } = parseEvents(text);
    expect(connected).toBe(true);
    expect(events).toEqual([expect.objectContaining({ id: "e1", recording_id: "r1", status: "ANALYZING" })]);
    expect(rest).toBe('id: e2\nevent: status\ndata: {"ty');
  });

  it("skips a malformed event", () => {
    expect(parseEvents("id: e1\ndata: {not json\n\n").events).toEqual([]);
  });
});

describe("affectedQueries", () => {
  it("refreshes the lists, the recording and the review queue when one needs review", () => {
    const keys = affectedQueries({ id: "e", type: "recording.needs_review", recording_id: "r1", status: "NEEDS_REVIEW",
                                   reason: "unclear_roles", at: "" }); // prettier-ignore
    expect(keys).toEqual(
      expect.arrayContaining([["recordings"], ["recording", "r1"], ["analysis", "r1"], ["reviews"]]),
    );
  });

  it("refreshes the people page when a report is done, and disputes when one is decided", () => {
    const done = affectedQueries({ id: "e", type: "recording.completed", recording_id: "r1", status: "COMPLETED", reason: null, at: "" }); // prettier-ignore
    expect(done).toEqual(expect.arrayContaining([["people-summary"]]));
    const dispute = affectedQueries({ id: "e", type: "dispute.resolved", recording_id: "r1", status: null, reason: null, at: "" }); // prettier-ignore
    expect(dispute).toEqual(expect.arrayContaining([["disputes"]]));
  });
});

describe("connectLive", () => {
  it("refreshes queries on each event and reconnects at once with Last-Event-ID when the server ends a stream", async () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
    const calls: (Record<string, string> | undefined)[] = [];
    let second: () => void = () => {};
    const reconnected = new Promise<void>((resolve) => (second = resolve));
    const fetchImpl = vi.fn(async (_path: RequestInfo | URL, init?: RequestInit) => {
      calls.push(init?.headers as Record<string, string>);
      if (calls.length === 1)
        return streamResponse([": connected\n\n", EVENT("e1", "ANALYZING"), EVENT("e2", "COMPLETED")]);
      second();
      return new Promise<Response>(() => {}); // stays open
    });
    stop = connectLive({ token: "t", queryClient, fetchImpl, sleep: async () => {} });
    await reconnected;
    expect(calls[0]?.Authorization).toBe("Bearer t");
    expect(calls[0]?.["Last-Event-ID"]).toBeUndefined();
    expect(calls[1]?.["Last-Event-ID"]).toBe("e2");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["recording", "r1"] });
    expect(isLive()).toBe(true);
  });

  it("falls back to polling when live updates are unavailable, and tries again later", async () => {
    const waits: number[] = [];
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ code: "live_unavailable" }), { status: 503 }));
    let waited: () => void = () => {};
    const done = new Promise<void>((resolve) => (waited = resolve));
    stop = connectLive({ token: "t", queryClient: new QueryClient(), fetchImpl, sleep: async (ms) => {
      waits.push(ms);
      if (waits.length === 2) waited();
      return new Promise((resolve) => setTimeout(resolve, 0));
    } }); // prettier-ignore
    await done;
    expect(waits).toEqual([UNAVAILABLE_RETRY_MS, UNAVAILABLE_RETRY_MS]);
    expect(isLive()).toBe(false);
  });

  it("backs off after errors, and a reply that is not a stream is not retried at once", async () => {
    const waits: number[] = [];
    const fetchImpl = vi.fn(
      async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    let waited: () => void = () => {};
    const done = new Promise<void>((resolve) => (waited = resolve));
    stop = connectLive({ token: "t", queryClient: new QueryClient(), fetchImpl, sleep: async (ms) => {
      waits.push(ms);
      if (waits.length === 3) waited();
    } }); // prettier-ignore
    await done;
    expect(waits).toEqual(BACKOFF_MS.slice(0, 3));
  });

  it("stops when the session is no longer valid", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}", { status: 401 }));
    stop = connectLive({ token: "t", queryClient: new QueryClient(), fetchImpl, sleep: async () => {} });
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
