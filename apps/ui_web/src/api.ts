export type AuthUser = {
  id: number;
  username: string;
  email: string;
  mobile_number?: string;
  whatsapp_id?: string;
  telegram_chat_id?: string;
  is_admin: boolean;
  is_active?: boolean;
  force_password_change: boolean;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type AdminUser = {
  id: number;
  username: string;
  email: string;
  mobile_number: string;
  telegram_chat_id: string;
  whatsapp_number: string;
  is_active: boolean;
  is_admin: boolean;
  force_password_change: boolean;
  role_id?: number | null;
  role?: string;
  shift_id?: number | null;
  shift?: string;
  department_id?: number | null;
  department?: string;
  created_at?: string;
  last_login?: string;
};

export type AdminUsersResponse = {
  count: number;
  users: AdminUser[];
  shift_options?: Array<{ id: number; name: string }>;
  department_options?: Array<{ id: number; name: string }>;
};

export type HistoryItem = {
  id: number;
  title: string;
  created_at: string;
  interface?: string;
};

export type HistoryDetail = {
  history: Record<string, unknown>;
  messages: Array<{ id: number; role: string; content: string; timestamp: string }>;
};

export type RuntimeTraceItem = {
  idx?: number;
  eventType: string;
  payload: Record<string, unknown>;
};

export type HistoryResumeResponse = HistoryDetail & {
  ok: boolean;
  session_id: string;
  chat_lines: Array<{ id: number; role: "user" | "assistant"; text: string; timestamp: string }>;
};

export type SessionItem = {
  user_id: string;
  user: string;
  channel: string;
  session_id: string;
  last_message: string;
  last_access_utc: string;
  idle_seconds: number;
  chat_history?: string;
};

export type IntegrationStatus = {
  telegram: Record<string, unknown>;
  whatsapp: Record<string, unknown>;
  scheduler: Record<string, unknown>;
  api: Record<string, unknown>;
};

export type AgentItem = {
  id: number;
  name: string;
  description: string;
  prompt_content: string;
  version: number;
  is_active: number;
  created_at?: string;
  tools: string[];
};

export type RoleItem = {
  id: number;
  name: string;
  description: string;
  agents: string[];
};

export type ToolItem = {
  name: string;
  description: string;
  input_schema: string;
  output_schema: string;
  version: string;
  example_call: string;
};

export type SchedulerItem = {
  id: number;
  title: string;
  nl_request?: string;
  task_prompt: string;
  schedule_type: string;
  interval_minutes: number;
  run_hour: number;
  run_minute: number;
  run_day_of_week: number;
  days_of_week?: string;
  run_day_of_month: number;
  timezone: string;
  is_enabled: number;
  next_run_at?: string;
  last_run_at?: string;
  last_result?: string;
};

declare global {
  interface Window {
    __OASIS_RUNTIME_CONFIG__?: {
      apiBaseUrl?: string;
      apiPort?: number | string;
    };
  }
}

function resolveRuntimeApiBase(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const runtime = window.__OASIS_RUNTIME_CONFIG__;
  const configuredBase = String(runtime?.apiBaseUrl || "").trim();
  if (configuredBase) {
    return configuredBase.replace(/\/+$/, "");
  }

  const configuredPort = String(runtime?.apiPort || "").trim();
  if (configuredPort && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:${configuredPort}`;
  }

  return "";
}

function resolveDefaultApiBase(): string {
  const runtime = resolveRuntimeApiBase();
  if (runtime) {
    return runtime;
  }
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (configured) {
    return configured;
  }
  if (typeof window !== "undefined" && window.location?.port === "5199") {
    return "";
  }
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8787`;
  }
  return "http://127.0.0.1:8787";
}

const API_BASE = resolveDefaultApiBase();

export function getApiBase(): string {
  return API_BASE;
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Network error while calling ${API_BASE}${path}: ${message}`);
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const json = await res.json();
      if (json?.detail) {
        detail = String(json.detail);
      }
    } catch {
      // no-op
    }
    throw new Error(detail);
  }

  return (await res.json()) as T;
}

export async function login(loginValue: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ login: loginValue, password }),
  });
}

export async function getMe(token: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/me", { method: "GET" }, token);
}

export async function logout(token: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/auth/logout", { method: "POST" }, token);
}

export async function changePassword(token: string, currentPassword: string, newPassword: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    "/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    },
    token,
  );
}

export async function getSettings(token: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/settings", { method: "GET" }, token);
}

export async function updateSettings(token: string, values: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(
    "/settings",
    {
      method: "PUT",
      body: JSON.stringify({ values }),
    },
    token,
  );
}

export async function listUsers(token: string): Promise<AdminUsersResponse> {
  return request<AdminUsersResponse>("/admin/users", { method: "GET" }, token);
}

export async function createUser(
  token: string,
  payload: {
    username: string;
    email?: string;
    is_admin: boolean;
    mobile_number?: string;
    whatsapp_number?: string;
    telegram_chat_id?: string;
  },
): Promise<{
  user: AdminUser;
  password_sent: boolean;
  delivery_note: string;
  temporary_password: string;
}> {
  return request(
    "/admin/users",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export async function sendNewPassword(token: string, userId: number): Promise<{ ok: boolean; temporary_password: string; password_sent: boolean; delivery_note: string }> {
  return request(
    `/admin/users/${userId}/send-new-password`,
    {
      method: "POST",
    },
    token,
  );
}

export async function updateUser(token: string, userId: number, payload: Record<string, unknown>): Promise<{ ok: boolean }> {
  return request(`/uiport/users/${userId}`, { method: "PUT", body: JSON.stringify(payload) }, token);
}

export async function getTabManifest(token: string): Promise<{ sidebar: string[]; settings_tabs: string[] }> {
  return request("/uiport/tab-manifest", { method: "GET" }, token);
}

export async function listHistory(token: string): Promise<{ count: number; items: HistoryItem[] }> {
  return request("/uiport/history", { method: "GET" }, token);
}

export async function getHistory(token: string, chatId: number): Promise<HistoryDetail> {
  return request(`/uiport/history/${chatId}`, { method: "GET" }, token);
}

export async function getHistoryRuntimeLog(token: string, chatId: number): Promise<{ trace: RuntimeTraceItem[]; available: boolean }> {
  return request(`/uiport/history/${chatId}/runtime-log`, { method: "GET" }, token);
}

async function downloadTraceFile(token: string, path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      message = String(body?.detail || message);
    } catch {
      // no-op
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const filename = /filename=\"?([^\";]+)\"?/i.exec(disposition)?.[1] || "runtime-trace.txt";
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function downloadChatTraceFile(token: string, requestId: string, filepath: string): Promise<void> {
  return downloadTraceFile(token, `/uiport/chat/status/${encodeURIComponent(requestId)}/trace-file?path=${encodeURIComponent(filepath)}`);
}

export async function downloadHistoryTraceFile(token: string, chatId: number, filepath: string): Promise<void> {
  return downloadTraceFile(token, `/uiport/history/${chatId}/runtime-file?path=${encodeURIComponent(filepath)}`);
}

export async function resumeHistory(token: string, chatId: number): Promise<HistoryResumeResponse> {
  return request(`/uiport/history/${chatId}/resume`, { method: "POST" }, token);
}

export async function listSessions(token: string): Promise<{ count: number; items: SessionItem[] }> {
  return request("/uiport/sessions", { method: "GET" }, token);
}

export async function listLogs(token: string): Promise<{ logs: Record<string, string> }> {
  return request("/uiport/logs", { method: "GET" }, token);
}

export async function readLog(token: string, name: string, lines = 250): Promise<{ name: string; path: string; content: string }> {
  return request("/uiport/logs/read", { method: "POST", body: JSON.stringify({ name, lines }) }, token);
}

export async function getIntegrationsStatus(token: string): Promise<IntegrationStatus> {
  return request("/uiport/integrations/status", { method: "GET" }, token);
}

export async function getServiceStatus(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/services/status", { method: "GET" }, token);
}

export async function stopApiService(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/services/api/stop", { method: "POST" }, token);
}

export async function restartApiService(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/services/api/restart", { method: "POST" }, token);
}

export async function stopWebUiService(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/services/web-ui/stop", { method: "POST" }, token);
}

export async function restartWebUiService(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/services/web-ui/restart", { method: "POST" }, token);
}
export async function restartTelegram(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/telegram/restart", { method: "POST" }, token);
}

export async function stopTelegram(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/telegram/stop", { method: "POST" }, token);
}

export async function testTelegram(token: string, chatId: string, message: string): Promise<Record<string, unknown>> {
  return request(
    "/uiport/integrations/telegram/test-send",
    { method: "POST", body: JSON.stringify({ chat_id: chatId, message }) },
    token,
  );
}

export async function testEmail(token: string, to: string, subject: string, body: string): Promise<Record<string, unknown>> {
  return request(
    "/uiport/integrations/email/test-send",
    { method: "POST", body: JSON.stringify({ to, subject, body }) },
    token,
  );
}

export async function restartWhatsApp(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/restart", { method: "POST" }, token);
}

export async function stopWhatsApp(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/stop", { method: "POST" }, token);
}

export async function testWhatsApp(token: string, to: string, message: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/test-send", { method: "POST", body: JSON.stringify({ to, message }) }, token);
}



export async function getWhatsAppHeadlessStatus(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/headless/status", { method: "GET" }, token);
}

export async function startWhatsAppHeadlessRegister(token: string, phoneNumber: string, baseFolder = ""): Promise<Record<string, unknown>> {
  return request(
    "/uiport/integrations/whatsapp/headless/register/start",
    { method: "POST", body: JSON.stringify({ phone_number: phoneNumber, base_folder: baseFolder }) },
    token,
  );
}

export async function stopWhatsAppHeadlessRegister(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/headless/register/stop", { method: "POST" }, token);
}

export async function logoutWhatsAppHeadless(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/headless/logout", { method: "POST" }, token);
}
export async function startWhatsAppHeadlessDaemon(token: string, baseFolder = ""): Promise<Record<string, unknown>> {
  return request(
    "/uiport/integrations/whatsapp/headless/daemon/start",
    { method: "POST", body: JSON.stringify({ base_folder: baseFolder }) },
    token,
  );
}

export async function stopWhatsAppHeadlessDaemon(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/integrations/whatsapp/headless/daemon/stop", { method: "POST" }, token);
}

export async function sendWebChat(
  token: string,
  payload: { session_id: string; message: string; files?: Array<Record<string, unknown>> },
): Promise<Record<string, unknown>> {
  return request("/uiport/chat/send", { method: "POST", body: JSON.stringify(payload) }, token);
}

export async function getWebChatStatus(token: string, requestId: string): Promise<Record<string, unknown>> {
  return request(`/uiport/chat/status/${encodeURIComponent(requestId)}`, { method: "GET" }, token);
}

export async function stopWebChat(token: string, sessionId: string): Promise<Record<string, unknown>> {
  return request("/uiport/chat/stop", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }, token);
}

export async function listAgents(token: string): Promise<{ count: number; items: AgentItem[] }> {
  return request("/uiport/agents", { method: "GET" }, token);
}

export async function getAgent(token: string, name: string): Promise<{ agent: AgentItem; versions: Array<{ id: number; version: number; created_at: string; prompt_content: string }> }> {
  return request(`/uiport/agents/${encodeURIComponent(name)}`, { method: "GET" }, token);
}

export async function saveAgent(token: string, payload: { name: string; description: string; prompt_content: string; is_active: boolean; tools: string[] }): Promise<Record<string, unknown>> {
  return request("/uiport/agents", { method: "POST", body: JSON.stringify(payload) }, token);
}

export async function deactivateAgent(token: string, name: string): Promise<Record<string, unknown>> {
  return request(`/uiport/agents/${encodeURIComponent(name)}/deactivate`, { method: "POST" }, token);
}

export async function restoreAgent(token: string, name: string, version: number): Promise<Record<string, unknown>> {
  return request(`/uiport/agents/${encodeURIComponent(name)}/restore`, { method: "POST", body: JSON.stringify({ version }) }, token);
}

export async function listRoles(token: string): Promise<{ count: number; items: RoleItem[] }> {
  return request("/uiport/roles", { method: "GET" }, token);
}

export async function saveRole(token: string, payload: { name: string; description: string; agent_names: string[] }): Promise<Record<string, unknown>> {
  return request("/uiport/roles", { method: "POST", body: JSON.stringify(payload) }, token);
}

export async function deleteRole(token: string, roleId: number): Promise<Record<string, unknown>> {
  return request(`/uiport/roles/${roleId}`, { method: "DELETE" }, token);
}

export async function listTools(token: string): Promise<{ count: number; items: ToolItem[] }> {
  return request("/uiport/tools", { method: "GET" }, token);
}

export async function refreshTools(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/tools/refresh", { method: "POST" }, token);
}

export async function updateToolDescription(token: string, name: string, description: string): Promise<Record<string, unknown>> {
  return request(`/uiport/tools/${encodeURIComponent(name)}/description`, { method: "PUT", body: JSON.stringify({ description }) }, token);
}

export async function getSchedulerStatus(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler/status", { method: "GET" }, token);
}

export async function restartScheduler(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler/restart", { method: "POST" }, token);
}

export async function stopScheduler(token: string): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler/stop", { method: "POST" }, token);
}

export async function listSchedules(token: string): Promise<{ count: number; items: SchedulerItem[] }> {
  return request("/uiport/scheduler", { method: "GET" }, token);
}

export async function validateSchedule(token: string, text: string): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler/validate", { method: "POST", body: JSON.stringify({ request: text }) }, token);
}

export async function createScheduleFromRequest(token: string, text: string): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler/agent-create", { method: "POST", body: JSON.stringify({ request: text }) }, token);
}

export async function createSchedule(token: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request("/uiport/scheduler", { method: "POST", body: JSON.stringify(payload) }, token);
}

export async function updateSchedule(token: string, id: number, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return request(`/uiport/scheduler/${id}`, { method: "PUT", body: JSON.stringify(payload) }, token);
}

export async function deleteSchedule(token: string, id: number): Promise<Record<string, unknown>> {
  return request(`/uiport/scheduler/${id}`, { method: "DELETE" }, token);
}

export async function runScheduleNow(token: string, id: number): Promise<Record<string, unknown>> {
  return request(`/uiport/scheduler/${id}/run`, { method: "POST" }, token);
}

export async function listScheduleRuns(token: string): Promise<{ items: Record<string, unknown>[] }> {
  return request("/uiport/scheduler/runs", { method: "GET" }, token);
}

export async function retryScheduleRun(token: string, id: number): Promise<Record<string, unknown>> {
  return request(`/uiport/scheduler/runs/${id}/retry`, { method: "POST" }, token);
}







