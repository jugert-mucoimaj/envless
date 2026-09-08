import type {
  AccessToken,
  ActivityEvent,
  Consumer,
  Environment,
  EnvironmentStatus,
  ImportResult,
  IssuedToken,
  Project,
  Revision,
  Variable,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_ENVLESS_API?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

/** An API error carrying the message the backend wrote, ready to show. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readDetail(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  // Pydantic sends validation problems as a list; the message is the useful part.
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg.replace(/^Value error,\s*/, "");
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the envless API. Is the backend running on port 8000?", 0);
  }

  if (!response.ok) {
    let message = `The API returned ${response.status}.`;
    try {
      message = readDetail(await response.json()) ?? message;
    } catch {
      /* keep the status-line message */
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),

  createProject: (body: { name: string; slug: string; description?: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),

  deleteProject: (projectId: string) =>
    request<void>(`/api/projects/${projectId}`, { method: "DELETE" }),

  createEnvironment: (
    projectId: string,
    body: { name: string; slug: string; aspect: string; rank: number },
  ) =>
    request<Environment>(`/api/projects/${projectId}/environments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateEnvironment: (
    environmentId: string,
    body: Partial<{ name: string; aspect: string; rank: number }>,
  ) =>
    request<Environment>(`/api/environments/${environmentId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteEnvironment: (environmentId: string) =>
    request<void>(`/api/environments/${environmentId}`, { method: "DELETE" }),

  listVariables: (environmentId: string, reveal = false) =>
    request<Variable[]>(`/api/environments/${environmentId}/variables?reveal=${reveal}`),

  createVariable: (
    environmentId: string,
    body: { key: string; value: string; is_secret: boolean; note?: string },
  ) =>
    request<Variable>(`/api/environments/${environmentId}/variables`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateVariable: (
    environmentId: string,
    variableId: string,
    body: Partial<{ key: string; value: string; is_secret: boolean; note: string }>,
  ) =>
    request<Variable>(`/api/environments/${environmentId}/variables/${variableId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  revealVariable: (environmentId: string, variableId: string) =>
    request<Variable>(
      `/api/environments/${environmentId}/variables/${variableId}?reveal=true`,
    ),

  deleteVariable: (environmentId: string, variableId: string) =>
    request<void>(`/api/environments/${environmentId}/variables/${variableId}`, {
      method: "DELETE",
    }),

  importVariables: (environmentId: string, body: string, overwrite: boolean) =>
    request<ImportResult>(`/api/environments/${environmentId}/variables/import`, {
      method: "POST",
      body: JSON.stringify({ body, overwrite, mark_secret: true }),
    }),

  environmentStatus: (environmentId: string) =>
    request<EnvironmentStatus>(`/api/environments/${environmentId}/status`),

  history: (environmentId: string) =>
    request<Revision[]>(`/api/environments/${environmentId}/history?limit=40`),

  activity: (limit = 40) => request<ActivityEvent[]>(`/api/activity?limit=${limit}`),

  alerts: (limit = 40) =>
    request<ActivityEvent[]>(`/api/activity?alerts_only=true&limit=${limit}`),

  consumers: (environmentId: string) =>
    request<Consumer[]>(`/api/environments/${environmentId}/consumers`),

  listTokens: (environmentId: string) =>
    request<AccessToken[]>(`/api/environments/${environmentId}/tokens`),

  issueToken: (environmentId: string, name: string) =>
    request<IssuedToken>(`/api/environments/${environmentId}/tokens`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  revokeToken: (environmentId: string, tokenId: string) =>
    request<void>(`/api/environments/${environmentId}/tokens/${tokenId}`, { method: "DELETE" }),

  exportUrl: (environmentId: string, format: "dotenv" | "json") =>
    `${API_BASE}/api/environments/${environmentId}/export?format=${format}`,

  health: () => request<{ status: string; database: string }>("/health"),
};
