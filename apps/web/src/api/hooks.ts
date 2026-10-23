// TanStack Query hooks for the API (P6.2). Every request carries the session's token; recordings still moving
// through the pipeline are refetched every REFRESH_MS so statuses update without a reload (SSE comes with P2.6).

import { useInfiniteQuery, useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { AnalysisPayload } from "../features/report/types";
import { useSession } from "../session/session";
import { ApiError, apiFetch } from "./client";
import {
  IN_PROGRESS,
  type DevUser,
  type Me,
  type PersonItem,
  type PersonSummary,
  type RecordingDetail,
  type RecordingPage,
  type TranscriptResponse,
} from "./types";

export const REFRESH_MS = 10_000;

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
      query.state.data?.pages.some((page) => page.items.some((item) => IN_PROGRESS.has(item.status)))
        ? REFRESH_MS
        : false,
  });
}

export function useRecording(id: string): UseQueryResult<RecordingDetail, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["recording", id, token],
    queryFn: () => apiFetch<RecordingDetail>(`/v1/recordings/${encodeURIComponent(id)}`, { token }),
    enabled: Boolean(token),
    refetchInterval: (query) => (query.state.data && IN_PROGRESS.has(query.state.data.status) ? REFRESH_MS : false),
  });
}

export function useAnalysis(id: string): UseQueryResult<AnalysisPayload, ApiError> {
  const { token } = useSession();
  return useQuery({
    queryKey: ["analysis", id, token],
    queryFn: () => apiFetch<AnalysisPayload>(`/v1/recordings/${encodeURIComponent(id)}/analysis`, { token }),
    enabled: Boolean(token),
    refetchInterval: (query) => (query.state.data?.status === "processing" ? REFRESH_MS : false),
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

/** The local dev sign-in's people (dev mode only). */
export function useDevUsers(enabled: boolean): UseQueryResult<DevUser[], ApiError> {
  return useQuery({
    queryKey: ["dev-users"],
    queryFn: () => apiFetch<DevUser[]>("/dev-idp/users"),
    enabled,
  });
}
