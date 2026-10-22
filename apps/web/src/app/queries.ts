// The query client (P6.2). Query errors are announced as a window event so a component inside the toast and
// session providers can show them (app/App.tsx ApiErrors), without the client holding React state.

import { QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";

export const API_ERROR_EVENT = "sabha:api-error";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 4xx answers will not change on retry; network and server errors get two more tries.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
    queryCache: new QueryCache({
      onError: (error) => window.dispatchEvent(new CustomEvent<unknown>(API_ERROR_EVENT, { detail: error })),
    }),
  });
}
