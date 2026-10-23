// The API client (P6.2): one fetch wrapper that adds the access token and turns problem+json errors (RFC 9457,
// sabha_api.errors) into ApiError, so pages can show the message and the request id in a toast.
// Requests go to the same origin: Vite proxies /v1 and /dev-idp to the API in development (vite.config.ts).

/** An error response from the API, with its stable `code` and the `request_id` to quote to support. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly requestId: string | undefined;

  constructor(status: number, code: string, title: string, detail: string, requestId?: string) {
    super(detail || title);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.title = title;
    this.requestId = requestId;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  token?: string;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

/** Calls the API and returns the parsed JSON body; throws ApiError for any non-2xx answer. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "No connection", "The server could not be reached. Check your connection.");
  }
  if (response.ok) {
    return (response.status === 204 ? undefined : await response.json()) as T;
  }
  let problem: Record<string, unknown> = {};
  try {
    problem = (await response.json()) as Record<string, unknown>;
  } catch {
    // not JSON (a proxy error page, for example): fall back to the status line
  }
  const text = (key: string) => (typeof problem[key] === "string" ? (problem[key] as string) : "");
  throw new ApiError(
    response.status,
    text("code") || `http_${response.status}`,
    text("title") || response.statusText || "Request failed",
    text("detail"),
    text("request_id") || undefined,
  );
}
