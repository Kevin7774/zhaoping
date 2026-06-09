export const API_BASE_URL = import.meta.env.VITE_API_BASE ?? "/api";

export type QueryValue = string | number | boolean | null | undefined;

export type ApiRequestConfig = Omit<RequestInit, "body"> & {
  query?: Record<string, QueryValue>;
  body?: unknown;
};

export type RequestInterceptor = (
  path: string,
  config: ApiRequestConfig,
) => ApiRequestConfig | Promise<ApiRequestConfig>;

export type ResponseInterceptor = (response: Response) => Response | Promise<Response>;

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

async function request<T>(path: string, config: ApiRequestConfig = {}): Promise<T> {
  const intercepted = await applyRequestInterceptors(path, config);
  const { body, query, ...fetchOptions } = intercepted;
  const headers = normalizeHeaders(fetchOptions.headers);

  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // JWT placeholder: auth is not enabled in the current backend contract.
  // When the app adds login, set jwtTokenProvider to inject Authorization.
  const token = jwtTokenProvider ? await jwtTokenProvider() : null;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`, {
    ...fetchOptions,
    method: fetchOptions.method ?? (body === undefined ? "GET" : "POST"),
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return parseResponse<T>(await applyResponseInterceptors(response));
}

export const apiClient = {
  request,
  get: <T>(path: string, config?: ApiRequestConfig) => request<T>(path, { ...config, method: "GET" }),
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
};

export function taskStreamUrl(taskId: string) {
  return `${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}/stream`;
}
