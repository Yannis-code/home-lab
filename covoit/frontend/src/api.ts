const TOKEN_KEY = "covoit_token";

export const UNAUTHORIZED_EVENT = "covoit:unauthorized";

export class ApiError extends Error {}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

export type QueryParams = Record<string, string | number | undefined | null>;

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: QueryParams;
}

function buildUrl(path: string, params?: QueryParams): string {
  const entries = Object.entries(params ?? {}).filter(
    ([, value]) => value !== undefined && value !== null && value !== ""
  ) as [string, string | number][];
  if (entries.length === 0) return path;
  const search = new URLSearchParams(entries.map(([key, value]) => [key, String(value)])).toString();
  return `${path}?${search}`;
}

function extractErrorMessage(status: number, data: unknown): string {
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg: string }) => item.msg).join(", ");
  }
  return `Erreur ${status}`;
}

async function request<T>(path: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? JSON.parse(text) : text;

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(response.status, data));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: QueryParams) => request<T>(path, { params }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
