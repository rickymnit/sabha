// TanStack Query hooks for the API (P6.2). Every request carries the session's token. Recordings still moving
// through the pipeline update through the live stream (api/live.ts, P2.6); while there is none, they are refetched
// every REFRESH_MS instead.

import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect } from "react";

import type { ConversationType } from "../design";
import type { CostResponse, EstimateResponse } from "../features/costs/types";
import type { DisputeDraft, DisputePage, Resolution } from "../features/disputes/types";
import type { OverviewStats } from "../features/overview/types";
import type { AnalysisPayload } from "../features/report/types";
import { useSession } from "../session/session";
import { ApiError, apiFetch } from "./client";
import { connectLive, isLive } from "./live";
import {
  IN_PROGRESS,
  type AnalysisVersion,
  type AuditPage,
  type ApiStatus,
  type BulkReanalysisRequest,
  type BulkReanalysisResult,
  type DevUser,
  type Inbox,
  type Me,
  type PersonItem,
  type ProcessingInfo,
  type PersonSummary,
  type RecordingDetail,
  type RecordingCounts,
  type RecordingQuery,
  type RecordingPage,
  type RubricDetail,
  type RubricListItem,
  type SearchResults,
  type ReviewDecision,
  type SettingsChange,
  type SpeakersResponse,
  type TenantSettings,
  type TranscriptResponse,
  type UsageSummary,
  type MyCoaching,
  type MySummary,
  type NextActionItem,
  type ProductInfoItem,
  type ProductInfoList,
} from "./types";

export const REFRESH_MS = 5_000;

/** Polling only while the live stream is down (P2.6). */
function poll(): number | false {
  return isLive() ? false : REFRESH_MS;
}

/** Opens the live status stream for the signed-in session (P2.6); one per tab, from the app shell. */
export function useLiveEvents(enabled: boolean): void {
  const { token } = useSession();
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled || !token) return undefined;
    return connectLive({ token, queryClient });
  }, [enabled, token, queryClient]);
}

/** A fetcher bound to the current session's token. */
export function useApi(): <T>(path: string) => Promise<T> {
  const { token } = useSession();
  return <T>(path: string) => apiFetch<T>(path, { token });
}

export function useMe(): UseQueryResult<Me, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["me", token],
    queryFn: () => apiFetch<Me>("/v1/me", { token }),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
  });
}

/** Narrowing filters for the list; the API applies them on top of what the caller may see. */
export interface RecordingFilters {
  type?: string | null;
  personId?: string | null;
  /** Sales calls or meetings only. */
  interaction?: "call" | "meeting" | null;
}

export function useRecordings(filters: RecordingFilters = {}, pageSize = 20) {
  const { token } = useSession();
  const { type = null, personId = null, interaction = null } = filters;
  return useInfiniteQuery({
    queryKey: ["recordings", pageSize, type, personId, interaction, token],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(pageSize) });
      if (pageParam) params.set("cursor", pageParam);
      if (type) params.set("type", type);
      if (personId) params.set("person_id", personId);
      if (interaction) params.set("interaction", interaction);
      return apiFetch<RecordingPage>(`/v1/recordings?${params}`, { token });
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: Boolean(token),
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some((item) => IN_PROGRESS.has(item.status))) ? poll() : false,
  });
}

function recordingParams(query: RecordingQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value) params.set(key, String(value));
  return params;
}

/** One page of GET /v1/recordings with the page's filters, for Previous / Next paging by cursor. */
export function useRecordingsPage(
  query: RecordingQuery,
  cursor: string | null,
  pageSize = 10,
): UseQueryResult<RecordingPage, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recordings", "page", query, cursor, pageSize, token],
    queryFn: () => {
      const params = recordingParams(query);
      params.set("limit", String(pageSize));
      if (cursor) params.set("cursor", cursor);
      return apiFetch<RecordingPage>(`/v1/recordings?${params}`, { token });
    },
    enabled: Boolean(token),
    placeholderData: (previous) => previous,
    refetchInterval: (q) => (q.state.data?.items.some((item) => IN_PROGRESS.has(item.status)) ? poll() : false),
  });
}

/** GET /v1/recordings/export.csv with the page's filters, saved as a file. Audited by the API. */
export function useExportRecordings() {
  const { token } = useSession();
  return useMutation({
    mutationFn: async (query: RecordingQuery) => {
      let response: Response;
      try {
        response = await fetch(`/v1/recordings/export.csv?${recordingParams(query)}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } catch {
        throw new ApiError(0, "network_error", "No connection", "The server could not be reached.");
      }
      if (!response.ok) throw new ApiError(response.status, `http_${response.status}`, "Export failed", "");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `recordings-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

/** POST /v1/recordings/{id}/reanalyze for several recordings, one after another; resolves with how many started. */
export function useReanalyseMany() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ids, reason }: { ids: string[]; reason: string }) => {
      let started = 0;
      for (const id of ids) {
        await apiFetch(`/v1/recordings/${encodeURIComponent(id)}/reanalyze`, {
          method: "POST",
          token,
          body: { reason },
          headers: { "Idempotency-Key": crypto.randomUUID() },
        });
        started += 1;
      }
      return started;
    },
    onSettled: async () => {
      await Promise.all(
        ["recording", "analysis", "analysis-history", "recordings", "disputes"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

export function useRecording(id: string): UseQueryResult<RecordingDetail, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recording", id, token],
    queryFn: () => apiFetch<RecordingDetail>(`/v1/recordings/${encodeURIComponent(id)}`, { token }),
    enabled: Boolean(token),
    refetchInterval: (query) => (query.state.data && IN_PROGRESS.has(query.state.data.status) ? poll() : false),
  });
}

/** The report payload: the latest analysis, or an earlier version when `analysisId` is given (re-analysis). */
export function useAnalysis(id: string, analysisId?: string): UseQueryResult<AnalysisPayload, ApiError> {
  const { token } = useSession();
  const version = analysisId ? `?analysis_id=${encodeURIComponent(analysisId)}` : "";
  return useQuery({
    queryKey: ["analysis", id, analysisId ?? "latest", token],
    queryFn: () => apiFetch<AnalysisPayload>(`/v1/recordings/${encodeURIComponent(id)}/analysis${version}`, { token }),
    enabled: Boolean(token),
    refetchInterval: (query) => (query.state.data?.status === "processing" ? poll() : false),
  });
}

/** The transcript, or null while there is none yet (the API answers 404 until transcription is done). */
export function useTranscript(id: string, enabled: boolean): UseQueryResult<TranscriptResponse | null, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["transcript", id, token],
    queryFn: async () => {
      try {
        return await apiFetch<TranscriptResponse>(`/v1/recordings/${encodeURIComponent(id)}/transcript`, { token });
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled: Boolean(token) && enabled,
    staleTime: 60_000,
  });
}

export function usePeople(): UseQueryResult<PersonItem[], ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["people", token],
    queryFn: () => apiFetch<PersonItem[]>("/v1/people", { token }),
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
  });
}

export function usePeopleSummary(enabled = true): UseQueryResult<PersonSummary[], ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["people-summary", token],
    queryFn: () => apiFetch<PersonSummary[]>("/v1/people/summary", { token }),
    enabled: enabled && Boolean(token),
  });
}

/** The Overview numbers for a period; refreshed while something is being processed, so "Processing now" moves. */
export function useOverview(
  period: { from: string; to: string },
  unitId: string | null = null,
): UseQueryResult<OverviewStats, ApiError> {
  const { token } = useSession();
  const params = unitId ? { ...period, unit_id: unitId } : period;
  return useQuery({
    queryKey: ["overview", period.from, period.to, unitId, token],
    queryFn: () => apiFetch<OverviewStats>(`/v1/overview?${new URLSearchParams(params)}`, { token }),
    placeholderData: (previous) => previous,
    enabled: Boolean(token),
    refetchInterval: (query) =>
      query.state.data?.in_progress?.some((s) => s.stage !== "needs_review") ? poll() : false,
  });
}

/** Recordings waiting for a reviewer's decision (owners, admins, managers, reviewers; ADR 0007). */
export function useReviews(enabled = true): UseQueryResult<RecordingPage, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["reviews", token],
    queryFn: () => apiFetch<RecordingPage>("/v1/reviews?limit=100", { token }),
    enabled: enabled && Boolean(token),
    refetchInterval: 30_000,
  });
}

export function useSpeakers(id: string, enabled = true): UseQueryResult<SpeakersResponse, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["speakers", id, token],
    queryFn: () => apiFetch<SpeakersResponse>(`/v1/recordings/${encodeURIComponent(id)}/speakers`, { token }),
    enabled: enabled && Boolean(token),
  });
}

/** POST /v1/recordings/{id}/review; refreshes the queue, the lists and the recording afterwards. */
export function useResolveReview(id: string) {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (decision: ReviewDecision) =>
      apiFetch<{ recording_id: string; status: ApiStatus }>(`/v1/recordings/${encodeURIComponent(id)}/review`, {
        method: "POST",
        token,
        body: decision,
      }),
    onSuccess: async () => {
      await Promise.all(
        ["reviews", "recordings", "recording", "analysis", "overview"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

/** Disputes a reviewer may decide (GET /v1/disputes; owners, admins, managers, reviewers; P6.7). */
export function useDisputes(enabled = true): UseQueryResult<DisputePage, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["disputes", token],
    queryFn: () => apiFetch<DisputePage>("/v1/disputes?limit=100", { token }),
    enabled: enabled && Boolean(token),
    refetchInterval: 30_000,
  });
}

/** POST /v1/analyses/{id}/disputes, with an Idempotency-Key so a retry never raises it twice. */
export function useRaiseDispute(recordingId: string) {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ analysisId, draft }: { analysisId: string; draft: DisputeDraft }) =>
      apiFetch(`/v1/analyses/${encodeURIComponent(analysisId)}/disputes`, {
        method: "POST",
        token,
        body: draft,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      }),
    onSuccess: async () => {
      await Promise.all(
        [["analysis", recordingId], ["disputes"]].map((key) => queryClient.invalidateQueries({ queryKey: key })),
      );
    },
  });
}

/** POST /v1/disputes/{id}/resolve; refreshes the queue and every report and number it can change. */
export function useResolveDispute() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution: Resolution }) =>
      apiFetch(`/v1/disputes/${encodeURIComponent(id)}/resolve`, { method: "POST", token, body: resolution }),
    onSuccess: async () => {
      await Promise.all(
        ["disputes", "analysis", "recordings", "overview", "people-summary"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

/** Every analysis of a recording, newest first (GET /v1/recordings/{id}/analyses; re-analysis keeps them all). */
export function useAnalysisHistory(id: string, enabled = true): UseQueryResult<AnalysisVersion[], ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["analysis-history", id, token],
    queryFn: () => apiFetch<AnalysisVersion[]>(`/v1/recordings/${encodeURIComponent(id)}/analyses`, { token }),
    enabled: enabled && Boolean(token),
  });
}

/** POST /v1/recordings/{id}/reanalyze (owners and admins), with an Idempotency-Key. */
export function useReanalyse(recordingId: string) {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<{ recording_id: string; status: ApiStatus; analysis_run: number }>(
        `/v1/recordings/${encodeURIComponent(recordingId)}/reanalyze`,
        { method: "POST", token, body: { reason }, headers: { "Idempotency-Key": crypto.randomUUID() } },
      ),
    onSuccess: async () => {
      await Promise.all(
        ["recording", "analysis", "analysis-history", "recordings", "disputes"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

/** GET /v1/recordings/{id}/processing: stage runs, the latest failure and AI cost (owners and admins). */
export function useProcessing(id: string, enabled: boolean): UseQueryResult<ProcessingInfo, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recording", id, "processing", token],
    queryFn: () => apiFetch<ProcessingInfo>(`/v1/recordings/${encodeURIComponent(id)}/processing`, { token }),
    enabled: enabled && Boolean(token),
  });
}

/** POST /v1/recordings/{id}/retry or /abandon (owners and admins), with an Idempotency-Key and the reason. */
export function useFailedRecordingAction(recordingId: string, action: "retry" | "abandon") {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      apiFetch<{ recording_id: string; status: ApiStatus; stage: string }>(
        `/v1/recordings/${encodeURIComponent(recordingId)}/${action}`,
        { method: "POST", token, body: { reason }, headers: { "Idempotency-Key": crypto.randomUUID() } },
      ),
    onSuccess: async () => {
      await Promise.all(
        ["recording", "analysis", "recordings", "audit"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

/** POST /v1/erasure (owners): `confirm: false` only counts; `true` erases for good. */
export function useErasure() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: { scope: "recording" | "person"; id: string; reason: string; confirm: boolean }) =>
      apiFetch<{ erased: boolean; recordings: number; files: number }>("/v1/erasure", {
        method: "POST",
        token,
        body: request,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      }),
    onSuccess: async (result) => {
      if (!result.erased) return;
      await Promise.all(
        ["recordings", "people", "people-summary", "overview", "audit"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}

/** POST /v1/reanalysis: count (dry run) or start re-analysing a type's recordings scored with an older rubric. */
export function useBulkReanalyse() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BulkReanalysisRequest) =>
      apiFetch<BulkReanalysisResult>("/v1/reanalysis", {
        method: "POST",
        token,
        body: request,
        headers: { "Idempotency-Key": crypto.randomUUID() },
      }),
    onSuccess: async (_, request) => {
      if (request.dry_run) return;
      await Promise.all(["recordings", "overview"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
    },
  });
}

/** GET /v1/recordings/counts, for the menu. Under ["recordings"], so live status refreshes it with the lists. */
export function useRecordingCounts(): UseQueryResult<RecordingCounts, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recordings", "counts", token],
    queryFn: () => apiFetch<RecordingCounts>("/v1/recordings/counts", { token }),
    enabled: Boolean(token),
  });
}

/** GET /v1/costs/estimate: what a recording of this type and length is expected to cost. */
export function useCostEstimate(
  type: ConversationType,
  durationMs: number | null,
): UseQueryResult<EstimateResponse, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["costs", "estimate", type, durationMs, token],
    queryFn: () => apiFetch<EstimateResponse>(`/v1/costs/estimate?type=${type}&duration_ms=${durationMs}`, { token }),
    enabled: Boolean(token) && durationMs !== null && durationMs > 0,
    staleTime: 60_000,
  });
}

/** GET /v1/recordings/{id}/cost. Under ["recording", id], so live status refreshes it as the recording moves. */
export function useRecordingCost(id: string): UseQueryResult<CostResponse, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recording", id, "cost", token],
    queryFn: () => apiFetch<CostResponse>(`/v1/recordings/${encodeURIComponent(id)}/cost`, { token }),
    enabled: Boolean(token),
  });
}

/** GET /v1/inbox: the bell and "Needs your decision". Under ["recordings"], so live status and the review and
 * dispute decisions (which refresh the lists) refresh it too. */
export function useInbox(): UseQueryResult<Inbox, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recordings", "inbox", token],
    queryFn: () => apiFetch<Inbox>("/v1/inbox", { token }),
    enabled: Boolean(token),
  });
}

/** GET /v1/search: people and recordings by name (two characters or more), keeping the last answer while typing. */
export function useSearch(q: string): UseQueryResult<SearchResults, ApiError> {
  const { token } = useSession();
  const text = q.trim();
  return useQuery({
    queryKey: ["search", text, token],
    queryFn: () => apiFetch<SearchResults>(`/v1/search?q=${encodeURIComponent(text)}`, { token }),
    enabled: Boolean(token) && text.length >= 2,
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
}

/** GET /v1/usage: this month's audio hours, for the plan block (owners and admins). */
export function useUsage(enabled: boolean): UseQueryResult<UsageSummary, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["usage", token],
    queryFn: () => apiFetch<UsageSummary>("/v1/usage", { token }),
    enabled: enabled && Boolean(token),
  });
}

/** Filters for the activity log; the API applies them on top of the tenant scope. */
export interface AuditFilters {
  action?: string | null;
  actorUserId?: string | null;
  from?: string | null;
}

/** GET /v1/audit, page by page (owners and admins). */
export function useAudit(filters: AuditFilters = {}, pageSize = 50) {
  const { token } = useSession();
  const { action = null, actorUserId = null, from = null } = filters;
  return useInfiniteQuery({
    queryKey: ["audit", pageSize, action, actorUserId, from, token],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(pageSize) });
      if (pageParam) params.set("cursor", pageParam);
      if (action) params.set("action", action);
      if (actorUserId) params.set("actor_user_id", actorUserId);
      if (from) params.set("from", from);
      return apiFetch<AuditPage>(`/v1/audit?${params}`, { token });
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: Boolean(token),
  });
}

/** GET /v1/rubrics: the rubric in use for each of the organisation's conversation types. */
export function useRubrics(): UseQueryResult<{ items: RubricListItem[] }, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["rubrics", token],
    queryFn: () => apiFetch<{ items: RubricListItem[] }>("/v1/rubrics", { token }),
    enabled: Boolean(token),
    staleTime: 10 * 60_000, // rubric files change only with a release
  });
}

/** GET /v1/rubrics/{id}: one rubric with its scale, versions and changes. */
export function useRubric(id: string | undefined): UseQueryResult<RubricDetail, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["rubric", id, token],
    queryFn: () => apiFetch<RubricDetail>(`/v1/rubrics/${encodeURIComponent(id ?? "")}`, { token }),
    enabled: Boolean(token && id),
    staleTime: 10 * 60_000,
  });
}

/** GET /v1/settings: the organisation's name, words and conversation types (owners and admins). */
export function useSettings(): UseQueryResult<TenantSettings, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["settings", token],
    queryFn: () => apiFetch<TenantSettings>("/v1/settings", { token }),
    enabled: Boolean(token),
  });
}

/** PATCH /v1/settings. The menu and every page read the words from /v1/me, so it is refetched at once. */
export function useUpdateSettings() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (change: SettingsChange) =>
      apiFetch<TenantSettings>("/v1/settings", { method: "PATCH", token, body: change }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(["settings", token], saved);
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

/** Units (classes and sections) and people (teachers), for owners and admins: POST/PATCH /v1/units and /v1/people.
 * Units come from GET /v1/me and people from the people lists, so those are refreshed after each change. */
export function useOrganisation() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  const refresh = async () => {
    await Promise.all(
      [["me"], ["people"], ["people-summary"]].map((key) => queryClient.invalidateQueries({ queryKey: key })),
    );
  };
  const create = (path: string) => (body: object) =>
    apiFetch<{ id: string }>(path, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body,
    });
  return {
    createUnit: useMutation({
      mutationFn: create("/v1/units") as (body: { name: string; parent_id: string | null }) => Promise<{ id: string }>,
      onSuccess: refresh,
    }),
    renameUnit: useMutation({
      mutationFn: ({ id, name }: { id: string; name: string }) =>
        apiFetch(`/v1/units/${encodeURIComponent(id)}`, { method: "PATCH", token, body: { name } }),
      onSuccess: refresh,
    }),
    createPerson: useMutation({
      mutationFn: create("/v1/people") as (body: { name: string; unit_ids: string[] }) => Promise<{ id: string }>,
      onSuccess: refresh,
    }),
    changePerson: useMutation({
      mutationFn: ({ id, ...body }: { id: string; name?: string; unit_ids?: string[] }) =>
        apiFetch(`/v1/people/${encodeURIComponent(id)}`, { method: "PATCH", token, body }),
      onSuccess: refresh,
    }),
  };
}

/** The local dev sign-in's people (dev mode only). */
export function useDevUsers(enabled: boolean): UseQueryResult<DevUser[], ApiError> {
  return useQuery({
    queryKey: ["dev-users"],
    queryFn: () => apiFetch<DevUser[]>("/dev-idp/users"),
    enabled,
  });
}

/** GET /v1/product-info: the approved product information (owners and admins may include retired entries). */
export function useProductInfo(includeRetired = false): UseQueryResult<ProductInfoList, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["product-info", includeRetired, token],
    queryFn: () =>
      apiFetch<ProductInfoList>(`/v1/product-info${includeRetired ? "?include_retired=true" : ""}`, { token }),
    enabled: Boolean(token),
  });
}

/** Add, change or retire approved product information (owners and admins). */
export function useProductInfoChanges() {
  const { token } = useSession();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["product-info"] });
  return {
    add: useMutation({
      mutationFn: (body: { title: string; body: string }) =>
        apiFetch<ProductInfoItem>("/v1/product-info", {
          method: "POST",
          token,
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body,
        }),
      onSuccess: refresh,
    }),
    change: useMutation({
      mutationFn: ({ id, ...body }: { id: string; title?: string; body?: string; status?: "active" | "retired" }) =>
        apiFetch<ProductInfoItem>(`/v1/product-info/${encodeURIComponent(id)}`, { method: "PATCH", token, body }),
      onSuccess: refresh,
    }),
  };
}

/** GET /v1/me/next-actions: your own next actions from your sales calls and meetings. */
export function useMyNextActions(): UseQueryResult<{ items: NextActionItem[] }, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["my-next-actions", token],
    queryFn: () => apiFetch<{ items: NextActionItem[] }>("/v1/me/next-actions", { token }),
    enabled: Boolean(token),
  });
}

/** GET /v1/me/summary: your calls and meetings this week or month, and the one before. */
export function useMySummary(period: "week" | "month"): UseQueryResult<MySummary, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["my-summary", period, token],
    queryFn: () => apiFetch<MySummary>(`/v1/me/summary?period=${period}`, { token }),
    placeholderData: (previous) => previous,
    enabled: Boolean(token),
  });
}

/** GET /v1/me/coaching: your private coaching themes and practice points. */
export function useMyCoaching(): UseQueryResult<MyCoaching, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["my-coaching", token],
    queryFn: () => apiFetch<MyCoaching>("/v1/me/coaching", { token }),
    enabled: Boolean(token),
  });
}
