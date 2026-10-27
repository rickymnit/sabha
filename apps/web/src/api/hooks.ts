// TanStack Query hooks for the API (P6.2). Every request carries the session's token. Recordings still moving
// through the pipeline update through the live stream (api/live.ts, P2.6); while there is none, they are refetched
// every REFRESH_MS instead.

import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect } from "react";

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
  type Me,
  type PersonItem,
  type ProcessingInfo,
  type PersonSummary,
  type RecordingDetail,
  type RecordingCounts,
  type RecordingPage,
  type RubricDetail,
  type RubricListItem,
  type ReviewDecision,
  type SettingsChange,
  type SpeakersResponse,
  type TenantSettings,
  type TranscriptResponse,
  type UsageSummary,
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
}

export function useRecordings(filters: RecordingFilters = {}, pageSize = 20) {
  const { token } = useSession();
  const { type = null, personId = null } = filters;
  return useInfiniteQuery({
    queryKey: ["recordings", pageSize, type, personId, token],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(pageSize) });
      if (pageParam) params.set("cursor", pageParam);
      if (type) params.set("type", type);
      if (personId) params.set("person_id", personId);
      return apiFetch<RecordingPage>(`/v1/recordings?${params}`, { token });
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: Boolean(token),
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some((item) => IN_PROGRESS.has(item.status))) ? poll() : false,
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
export function useOverview(period: { from: string; to: string }): UseQueryResult<OverviewStats, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["overview", period.from, period.to, token],
    queryFn: () => apiFetch<OverviewStats>(`/v1/overview?${new URLSearchParams(period)}`, { token }),
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

/** The local dev sign-in's people (dev mode only). */
export function useDevUsers(enabled: boolean): UseQueryResult<DevUser[], ApiError> {
  return useQuery({
    queryKey: ["dev-users"],
    queryFn: () => apiFetch<DevUser[]>("/dev-idp/users"),
    enabled,
  });
}
