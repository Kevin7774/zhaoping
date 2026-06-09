export const API_BASE_URL = import.meta.env.VITE_API_BASE ?? "/api";

export type QueryValue = string | number | boolean | null | undefined;

export type ApiRequestConfig = Omit<RequestInit, "body"> & {
  query?: Record<string, QueryValue>;
  body?: unknown;
};

export type ApiResponseMeta<T> = {
  data: T;
  headers: Headers;
  status: number;
};

export type RequestInterceptor = (
  path: string,
  config: ApiRequestConfig,
) => ApiRequestConfig | Promise<ApiRequestConfig>;

export type ResponseInterceptor = (response: Response) => Response | Promise<Response>;

export type ApiRequestLogEntry = {
  method: string;
  path: string;
  requestSummary: unknown;
  responseSummary: unknown;
  status?: number;
};

export type ApiRequestLogListener = (entry: ApiRequestLogEntry) => void;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const requestInterceptors: RequestInterceptor[] = [];
const responseInterceptors: ResponseInterceptor[] = [];
const requestLogListeners: ApiRequestLogListener[] = [];

let jwtTokenProvider: (() => string | null | Promise<string | null>) | null = null;

function buildQueryString(query: ApiRequestConfig["query"] = {}) {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }

  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

function normalizeHeaders(headers?: HeadersInit) {
  return new Headers(headers);
}

async function parseError(response: Response) {
  try {
    const payload = await response.json();
    return {
      detail: payload?.detail ?? payload,
      message: typeof payload?.detail === "string" ? payload.detail : `HTTP ${response.status}`,
    };
  } catch {
    return {
      detail: response.statusText,
      message: response.statusText || `HTTP ${response.status}`,
    };
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await parseError(response);
    throw new ApiError(response.status, error.message, error.detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json() as Promise<T>;
  }

  return response.text() as Promise<T>;
}

async function applyRequestInterceptors(path: string, config: ApiRequestConfig) {
  let next = config;
  for (const interceptor of requestInterceptors) {
    next = await interceptor(path, next);
  }
  return next;
}

async function applyResponseInterceptors(response: Response) {
  let next = response;
  for (const interceptor of responseInterceptors) {
    next = await interceptor(next);
  }
  return next;
}

async function fetchResponse(path: string, config: ApiRequestConfig = {}): Promise<Response> {
  const intercepted = await applyRequestInterceptors(path, config);
  const { body, query, ...fetchOptions } = intercepted;
  const headers = normalizeHeaders(fetchOptions.headers);
  const method = fetchOptions.method ?? (body === undefined ? "GET" : "POST");

  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // JWT placeholder: auth is not enabled in the current backend contract.
  // When the app adds login, set jwtTokenProvider to inject Authorization.
  const token = jwtTokenProvider ? await jwtTokenProvider() : null;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const fullPath = `${path}${buildQueryString(query)}`;
  const response = await fetch(`${API_BASE_URL}${fullPath}`, {
    ...fetchOptions,
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  notifyRequestLogListeners({
    method,
    path: fullPath,
    requestSummary: summarizePayload(body ?? query ?? null),
    responseSummary: await summarizeResponse(response.clone()),
    status: response.status,
  });

  return applyResponseInterceptors(response);
}

async function request<T>(path: string, config: ApiRequestConfig = {}): Promise<T> {
  return parseResponse<T>(await fetchResponse(path, config));
}

async function requestWithMeta<T>(path: string, config: ApiRequestConfig = {}): Promise<ApiResponseMeta<T>> {
  const response = await fetchResponse(path, config);
  return {
    data: await parseResponse<T>(response),
    headers: response.headers,
    status: response.status,
  };
}

export const apiClient = {
  request,
  requestWithMeta,
  get: <T>(path: string, config?: ApiRequestConfig) => request<T>(path, { ...config, method: "GET" }),
  getWithMeta: <T>(path: string, config?: ApiRequestConfig) =>
    requestWithMeta<T>(path, { ...config, method: "GET" }),
  post: <T>(path: string, body?: unknown, config?: ApiRequestConfig) =>
    request<T>(path, { ...config, method: "POST", body }),
  put: <T>(path: string, body?: unknown, config?: ApiRequestConfig) =>
    request<T>(path, { ...config, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, config?: ApiRequestConfig) =>
    request<T>(path, { ...config, method: "PATCH", body }),
  delete: <T>(path: string, config?: ApiRequestConfig) => request<T>(path, { ...config, method: "DELETE" }),
  addRequestInterceptor: (interceptor: RequestInterceptor) => {
    requestInterceptors.push(interceptor);
    return () => {
      const index = requestInterceptors.indexOf(interceptor);
      if (index >= 0) requestInterceptors.splice(index, 1);
    };
  },
  addResponseInterceptor: (interceptor: ResponseInterceptor) => {
    responseInterceptors.push(interceptor);
    return () => {
      const index = responseInterceptors.indexOf(interceptor);
      if (index >= 0) responseInterceptors.splice(index, 1);
    };
  },
  setJwtTokenProvider: (provider: typeof jwtTokenProvider) => {
    jwtTokenProvider = provider;
  },
  addRequestLogListener: (listener: ApiRequestLogListener) => {
    requestLogListeners.push(listener);
    return () => {
      const index = requestLogListeners.indexOf(listener);
      if (index >= 0) requestLogListeners.splice(index, 1);
    };
  },
};

export function taskStreamUrl(taskId: string) {
  return `${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}/stream`;
}

function notifyRequestLogListeners(entry: ApiRequestLogEntry) {
  for (const listener of requestLogListeners) {
    listener(entry);
  }
}

async function summarizeResponse(response: Response) {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) {
    return response.statusText || `HTTP ${response.status}`;
  }
  try {
    return summarizePayload(await response.json());
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

function summarizePayload(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined) return value ?? null;
  if (typeof value === "string") return value.length > 160 ? `${value.slice(0, 160)}...` : value;
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: depth >= 1 ? undefined : value.slice(0, 2).map((item) => summarizePayload(item, depth + 1)),
    };
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const summary: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(record).slice(0, 12)) {
      if (/key|token|secret|password|credential/i.test(key)) {
        summary[key] = "[redacted]";
      } else if (/email/i.test(key) && typeof item === "string") {
        summary[key] = "[email redacted]";
      } else {
        summary[key] = depth >= 2 ? summarizeLeaf(item) : summarizePayload(item, depth + 1);
      }
    }
    return summary;
  }
  return String(value);
}

function summarizeLeaf(value: unknown) {
  if (Array.isArray(value)) return { type: "array", length: value.length };
  if (value && typeof value === "object") return { type: "object", keys: Object.keys(value).slice(0, 8) };
  return summarizePayload(value, 3);
}
