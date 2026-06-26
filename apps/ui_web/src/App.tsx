import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";

import {
  AdminUser,
  AgentItem,
  AuthUser,
  HistoryDetail,
  HistoryItem,
  IntegrationStatus,
  RoleItem,
  SchedulerItem,
  SessionItem,
  ToolItem,
  changePassword,
  createSchedule,
  createUser,
  deleteRole,
  deleteSchedule,
  getAgent,
  getApiBase,
  getHistory,
  getIntegrationsStatus,
  getMe,
  getSchedulerStatus,
  getServiceStatus,
  getSettings,
  getTabManifest,
  getWhatsAppHeadlessStatus,
  listAgents,
  listHistory,
  listLogs,
  listRoles,
  listSchedules,
  listSessions,
  listTools,
  listUsers,
  login,
  logout,
  logoutWhatsAppHeadless,
  readLog,
  refreshTools,
  restartApiService,
  restartScheduler,
  restartTelegram,
  restartWebUiService,
  restartWhatsApp,
  resumeHistory,
  restoreAgent,
  runScheduleNow,
  saveAgent,
  saveRole,
  sendWebChat,
  getWebChatStatus,
  sendNewPassword,
  startWhatsAppHeadlessDaemon,
  startWhatsAppHeadlessRegister,
  stopApiService,
  stopScheduler,
  stopTelegram,
  stopWebChat,
  stopWebUiService,
  stopWhatsApp,
  stopWhatsAppHeadlessRegister,
  stopWhatsAppHeadlessDaemon,
  testEmail,
  testTelegram,
  testWhatsApp,
  updateSchedule,
  updateSettings,
  updateToolDescription,
  updateUser,
  validateSchedule,
} from "./api";

type MainTab = "chat" | "history" | "sessions" | "logs" | "settings" | "profile";
type SettingsTab = "system" | "ai" | "agents" | "roles" | "users" | "tools" | "email" | "telegram" | "whatsapp" | "services" | "scheduler";

type ChatLine = {
  id: string;
  role: "system" | "user" | "assistant" | "error" | "status";
  text: string;
};

type ChatWorkspaceTab = "messages" | "trace";

type ChatTraceLine = {
  id: string;
  eventType: string;
  text: string;
};

type ChatAttachment = {
  filename: string;
  mime_type: string;
  size_bytes: number;
  data_base64: string;
};

const RENDERABLE_HTML_RE = /<\/?(table|thead|tbody|tr|th|td|p|br|strong|b|em|i|ul|ol|li|h[1-6])\b/i;
const ALLOWED_HTML_TAGS = new Set(["TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "P", "BR", "STRONG", "B", "EM", "I", "UL", "OL", "LI", "H1", "H2", "H3", "H4", "H5", "H6"]);
const ALLOWED_HTML_ATTRS = new Set(["border", "colspan", "rowspan"]);

function sanitizeAgentHtml(value: string): string {
  const source = String(value || "");
  if (typeof document === "undefined") return source;

  const template = document.createElement("template");
  template.innerHTML = source;

  const visit = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as HTMLElement;
        if (!ALLOWED_HTML_TAGS.has(el.tagName)) {
          el.replaceWith(document.createTextNode(el.textContent || ""));
          continue;
        }
        for (const attr of Array.from(el.attributes)) {
          if (!ALLOWED_HTML_ATTRS.has(attr.name.toLowerCase())) {
            el.removeAttribute(attr.name);
          }
        }
      }
      visit(child);
    }
  };

  visit(template.content);
  return template.innerHTML;
}

function ChatMessage({ role, text }: { role: ChatLine["role"]; text: string }) {
  const shouldRenderHtml = role === "assistant" && RENDERABLE_HTML_RE.test(text);
  if (!shouldRenderHtml) {
    return <div className={`chat-line ${role}`}>{text}</div>;
  }
  return <div className={`chat-line ${role} rendered-html`} dangerouslySetInnerHTML={{ __html: sanitizeAgentHtml(text) }} />;
}

type UserEditForm = {
  username: string;
  email: string;
  mobile_number: string;
  whatsapp_number: string;
  telegram_chat_id: string;
  is_active: boolean;
  is_admin: boolean;
  role_id: string;
  role: string;
  shift_id: string;
  shift: string;
  department_id: string;
  department: string;
};

type ScheduleForm = {
  id: number | null;
  title: string;
  task_prompt: string;
  schedule_type: string;
  interval_minutes: number;
  run_hour: number;
  run_minute: number;
  run_day_of_week: number;
  run_day_of_month: number;
  timezone: string;
  is_enabled: boolean;
  last_run_at: string;
  last_result: string;
};

const TOKEN_KEY = "das_web_token";
const APP_VERSION = "v0.1.12-20260626";

const MAIN_TABS: Array<{ id: MainTab; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "history", label: "History" },
  { id: "sessions", label: "Sessions" },
  { id: "logs", label: "Logs" },
  { id: "settings", label: "Settings" },
  { id: "profile", label: "Profile" },
];

const SETTINGS_TABS: Array<{ id: SettingsTab; label: string }> = [
  { id: "system", label: "System Settings" },
  { id: "ai", label: "AI Config" },
  { id: "agents", label: "Assistants/Agents" },
  { id: "roles", label: "Roles" },
  { id: "users", label: "Users" },
  { id: "tools", label: "System Tools" },
  { id: "email", label: "Email" },
  { id: "telegram", label: "Telegram" },
  { id: "whatsapp", label: "WhatsApp" },
  { id: "services", label: "Services" },
  { id: "scheduler", label: "Scheduler" },
];
type ServiceKey = "api" | "web_ui";
type SchedulerView = "list" | "create" | "editor";

const GEMINI_MODELS = [
  "gemini-3-flash-preview",
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "gemini-2.0-flash",
  "gemini-2.0-flash-lite",
  "Gemma 3",
];

const GROQ_MODELS = [
  "llama-3.3-70b-versatile",
  "llama-3.1-8b-instant",
  "deepseek-r1-distill-llama-70b",
];

const LOCAL_MODELS = ["local-model", "qwen3-4b-instruct-2507", "step3-vl-10b", "qwen2.5-14b-instruct-1m", "gpt-oss-20b"];

const OPENROUTER_MODELS: Array<{ id: string; label: string }> = [
  { id: "google/gemini-2.5-flash", label: "google/gemini-2.5-flash [fast, optimum]" },
  { id: "google/gemini-2.0-flash-lite-001", label: "google/gemini-2.0-flash-lite-001 [fast, low cost, medium accuracy $0.075]" },
  { id: "openai/gpt-oss-120b", label: "openai/gpt-oss-120b [medium fast, low cost, low accuracy $0.039]" },
  { id: "openai/gpt-oss-20b", label: "openai/gpt-oss-20b [medium fast, low cost, low accuracy $0.03]" },
  { id: "openrouter/hunter-alpha", label: "openrouter/hunter-alpha [slow, low accuracy, free]" },
  { id: "nvidia/nemotron-3-super-120b-a12b:free", label: "nvidia/nemotron-3-super-120b-a12b:free [slow, low accuracy, free]" },
  { id: "stepfun/step-3.5-flash:free", label: "stepfun/step-3.5-flash:free [high latency]" },
  { id: "stepfun/step-3.5-flash", label: "stepfun/step-3.5-flash [high latency]" },
  { id: "meta-llama/llama-3.3-70b-instruct", label: "meta-llama/llama-3.3-70b-instruct [fast]" },
];

const SHIFT_OPTIONS = ["General", "Morning", "Evening", "Night"];
const DEPARTMENT_OPTIONS = ["Administration", "HR", "Finance", "Operations", "Sales", "IT"];

function makeId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function showAlert(message: string): void {
  if (typeof window !== "undefined" && typeof window.alert === "function") {
    window.alert(message);
  }
}

function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function uniqueOptions(...groups: string[][]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const group of groups) {
    for (const item of group) {
      const value = String(item || "").trim();
      if (!value || seen.has(value.toLowerCase())) continue;
      seen.add(value.toLowerCase());
      result.push(value);
    }
  }
  return result;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function asBool(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(v)) return true;
    if (["0", "false", "no", "off"].includes(v)) return false;
  }
  return fallback;
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asString(item, "").trim()).filter(Boolean);
}

function normalizeFeedbackStatus(value: unknown): string {
  const normalized = asString(value, "").trim().toLowerCase();
  if (!normalized) return "working";
  if (normalized === "complete") return "completed";
  return normalized;
}

function composeStatusText(status: string, message: string, hint = ""): string {
  const cleanStatus = normalizeFeedbackStatus(status);
  const cleanMessage = asString(message, "").trim();
  const cleanHint = asString(hint, "").trim();
  const text = cleanHint ? [cleanMessage, cleanHint].filter(Boolean).join(" | ") : cleanMessage;
  if (!text) return `[${cleanStatus}]`;
  return `[${cleanStatus}] ${text}`;
}

function titleCaseStatus(value: string): string {
  const clean = asString(value, "").trim();
  if (!clean) return "";
  return clean
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function extractTemporaryPassword(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const data = payload as Record<string, unknown>;
  const candidates = [
    data.temporary_password,
    data.temporaryPassword,
    data.temp_password,
    data.password,
    data.new_password,
  ];
  for (const value of candidates) {
    const text = asString(value, "").trim();
    if (text) return text;
  }
  return "";
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => {
      const dataUrl = asString(reader.result, "");
      const base64 = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
      resolve(base64);
    };
    reader.readAsDataURL(file);
  });
}

function defaultUserEdit(): UserEditForm {
  return {
    username: "",
    email: "",
    mobile_number: "",
    whatsapp_number: "",
    telegram_chat_id: "",
    is_active: true,
    is_admin: false,
    role_id: "",
    role: "",
    shift_id: "",
    shift: "",
    department_id: "",
    department: "",
  };
}

function defaultSchedule(): ScheduleForm {
  return {
    id: null,
    title: "",
    task_prompt: "",
    schedule_type: "other",
    interval_minutes: 60,
    run_hour: 9,
    run_minute: 0,
    run_day_of_week: 0,
    run_day_of_month: 1,
    timezone: "Asia/Calcutta",
    is_enabled: true,
    last_run_at: "",
    last_result: "",
  };
}

export default function App() {
  const [booting, setBooting] = useState(true);
  const [token, setToken] = useState("");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authError, setAuthError] = useState("");

  const [loginId, setLoginId] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMsg, setPasswordMsg] = useState("");

  const [mainTab, setMainTab] = useState<MainTab>("chat");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("system");

  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [settingsMsg, setSettingsMsg] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [accessibleDirsText, setAccessibleDirsText] = useState("");

  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyDetail, setHistoryDetail] = useState<HistoryDetail | null>(null);
  const [historyMsg, setHistoryMsg] = useState("");

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionsMsg, setSessionsMsg] = useState("");

  const [logsMap, setLogsMap] = useState<Record<string, string>>({});
  const [selectedLog, setSelectedLog] = useState("");
  const [logLines, setLogLines] = useState(250);
  const [logContent, setLogContent] = useState("");
  const [logsMsg, setLogsMsg] = useState("");

  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);
  const [integrationsMsg, setIntegrationsMsg] = useState("");
  const [serviceStatus, setServiceStatus] = useState<Record<string, unknown>>({});
  const [whatsappHeadlessStatus, setWhatsAppHeadlessStatus] = useState<Record<string, unknown> | null>(null);
  const [whatsappHeadlessMsg, setWhatsAppHeadlessMsg] = useState("");
  const [whatsappRegisterPhone, setWhatsAppRegisterPhone] = useState("");
  const [whatsappHeadlessBusy, setWhatsAppHeadlessBusy] = useState("");

  const [chatInput, setChatInput] = useState("");
  const [chatLines, setChatLines] = useState<ChatLine[]>([]);
  const [chatTraceLines, setChatTraceLines] = useState<ChatTraceLine[]>([]);
  const activeChatRequestRef = useRef<string>("");
  const [chatWorkspaceTab, setChatWorkspaceTab] = useState<ChatWorkspaceTab>("messages");
  const [chatConnected, setChatConnected] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatAttachment, setChatAttachment] = useState<ChatAttachment | null>(null);
  const [chatAttachBusy, setChatAttachBusy] = useState(false);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usersMsg, setUsersMsg] = useState("");
  const [shiftLookupOptions, setShiftLookupOptions] = useState<Array<{ id: number; name: string }>>([]);
  const [departmentLookupOptions, setDepartmentLookupOptions] = useState<Array<{ id: number; name: string }>>([]);
  const [manualPasswordNotice, setManualPasswordNotice] = useState("");
  const [lastTempPassword, setLastTempPassword] = useState("");
  const [lastTempPasswordUser, setLastTempPasswordUser] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [userEdit, setUserEdit] = useState<UserEditForm>(defaultUserEdit);

  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [newMobile, setNewMobile] = useState("");
  const [newWhatsApp, setNewWhatsApp] = useState("");
  const [newTelegram, setNewTelegram] = useState("");

  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [agentsMsg, setAgentsMsg] = useState("");
  const [agentName, setAgentName] = useState("");
  const [agentDescription, setAgentDescription] = useState("");
  const [agentPrompt, setAgentPrompt] = useState("");
  const [agentActive, setAgentActive] = useState(true);
  const [agentToolsSelected, setAgentToolsSelected] = useState<string[]>([]);
  const [agentVersions, setAgentVersions] = useState<Array<{ id: number; version: number; created_at: string; prompt_content: string }>>([]);
  const [agentRestoreVersion, setAgentRestoreVersion] = useState("");

  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [rolesMsg, setRolesMsg] = useState("");
  const [roleId, setRoleId] = useState<number | null>(null);
  const [roleName, setRoleName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [roleAgentsSelected, setRoleAgentsSelected] = useState<string[]>([]);

  const [tools, setTools] = useState<ToolItem[]>([]);
  const [toolsMsg, setToolsMsg] = useState("");
  const [selectedToolName, setSelectedToolName] = useState("");
  const [toolDescriptionDraft, setToolDescriptionDraft] = useState("");

  const [schedulerStatus, setSchedulerStatus] = useState<Record<string, unknown>>({});
  const [schedulerItems, setSchedulerItems] = useState<SchedulerItem[]>([]);
  const [schedulerMsg, setSchedulerMsg] = useState("");
  const [schedulerView, setSchedulerView] = useState<SchedulerView>("list");
  const [scheduleNlRequest, setScheduleNlRequest] = useState("");
  const [scheduleForm, setScheduleForm] = useState<ScheduleForm>(defaultSchedule);
  const [aiRestartRequired, setAiRestartRequired] = useState(false);

  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const chatFileInputRef = useRef<HTMLInputElement | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string>(() => makeId());
  const sessionIdRef = useRef<string>(chatSessionId);
  const persistedSettingsRef = useRef<Record<string, unknown>>({});

  const apiBase = useMemo(() => getApiBase(), []);
  const isAdmin = Boolean(user?.is_admin);

  const s = (key: string, fallback = "") => asString(settings[key], fallback);
  const n = (key: string, fallback = 0) => asNumber(settings[key], fallback);
  const b = (key: string, fallback = false) => asBool(settings[key], fallback);

  useEffect(() => {
    sessionIdRef.current = chatSessionId;
  }, [chatSessionId]);

  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [chatLines]);

  function setSettingValue(key: string, value: unknown) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  function syncSettings(values: Record<string, unknown>) {
    persistedSettingsRef.current = values;
    setSettings(values);
    const dirs = Array.isArray(values.accessible_directories)
      ? values.accessible_directories.map((x) => asString(x)).filter((x) => x.trim())
      : [];
    setAccessibleDirsText(dirs.join("\n"));
  }

  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY) || "";
    if (!saved) {
      setBooting(false);
      return;
    }
    getMe(saved)
      .then((me) => {
        setToken(saved);
        setUser(me);
        setMustChangePassword(Boolean(me.force_password_change));
      })
      .catch(() => {
        sessionStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!token || !user || mustChangePassword) {
      setChatConnected(false);
      return;
    }
    setChatConnected(true);
  }, [token, user, mustChangePassword]);

  useEffect(() => {
    if (!token || !user || mustChangePassword) return;

    void getTabManifest(token).catch(() => {});

    if (mainTab === "history") void loadHistoryList();
    if (mainTab === "sessions") void loadSessionsList();
    if (mainTab === "logs") void loadLogsList();

    if (mainTab === "settings") {
      void loadSettingsData();
      if (settingsTab === "agents") {
        void loadAgentsList();
        void loadToolsList();
      }
      if (settingsTab === "roles") {
        void loadRolesList();
        void loadAgentsList();
      }
      if (settingsTab === "users" && isAdmin) {
        void loadUsersList();
        void loadRolesList();
      }
      if (settingsTab === "tools") void loadToolsList();
      if (["telegram", "whatsapp", "scheduler"].includes(settingsTab)) void loadIntegrationsStatus();
      if (settingsTab === "services") void loadServiceStatus();
      if (settingsTab === "whatsapp" && isAdmin) void loadWhatsAppHeadlessStatus();
      if (settingsTab === "scheduler") {
        void loadSchedulerStatus();
        void loadSchedulesList();
      }
    }
  }, [token, user, mustChangePassword, mainTab, settingsTab, isAdmin]);

  useEffect(() => {
    if (!token || !isAdmin || mainTab !== "settings" || settingsTab !== "whatsapp") return;
    let disposed = false;

    const tick = async () => {
      try {
        const payload = await getWhatsAppHeadlessStatus(token);
        if (disposed) return;
        const status = asRecord(payload.status);
        setWhatsAppHeadlessStatus(status);
        const statusSettings = asRecord(status.settings);
        const baseFolder = asString(statusSettings.base_folder, "").trim();
        if (baseFolder) {
          setSettings((prev) => (prev.whatsapp_folder_root === baseFolder ? prev : { ...prev, whatsapp_folder_root: baseFolder }));
        }
        const register = asRecord(status.register);
        const knownPhone = asString(register.phone_number, "").trim();
        if (knownPhone) {
          setWhatsAppRegisterPhone((prev) => (prev.trim() ? prev : knownPhone));
        }
      } catch (err) {
        if (disposed) return;
        setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to load headless WhatsApp status");
      }
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, 3000);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [token, isAdmin, mainTab, settingsTab]);

  useEffect(() => {
    if (!token || mainTab !== "settings") return;
    if (!["telegram", "whatsapp", "services", "scheduler"].includes(settingsTab)) return;
    let disposed = false;

    const tick = async () => {
      try {
        await loadIntegrationsStatus();
        if (!disposed && settingsTab === "services") {
          await loadServiceStatus();
        }
        if (!disposed && settingsTab === "scheduler") {
          await loadSchedulerStatus();
        }
      } catch {
        // Individual loaders already update UI state.
      }
    };

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, 3000);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [token, mainTab, settingsTab]);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setAuthError("");
    try {
      const res = await login(loginId, loginPassword);
      sessionStorage.setItem(TOKEN_KEY, res.access_token);
      setToken(res.access_token);
      setUser(res.user);
      setMustChangePassword(Boolean(res.user.force_password_change));
      setLoginPassword("");
      const nextSessionId = makeId();
      sessionIdRef.current = nextSessionId;
      setChatSessionId(nextSessionId);
      setChatLines([]);
      setChatTraceLines([]);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordMsg("");
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function handleLogout() {
    try {
      if (token) await logout(token);
    } catch {
      // ignore
    }
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setLoginPassword("");
    setMustChangePassword(false);
    setMainTab("chat");
    setSettingsTab("system");
    setSettings({});
    setAccessibleDirsText("");
    setHistoryItems([]);
    setHistoryDetail(null);
    setSessions([]);
    setLogsMap({});
    setSelectedLog("");
    setLogContent("");
    setIntegrations(null);
    setWhatsAppHeadlessStatus(null);
    setWhatsAppHeadlessMsg("");
    setWhatsAppRegisterPhone("");
    setWhatsAppHeadlessBusy("");
    setUsers([]);
    setManualPasswordNotice("");
    setLastTempPassword("");
    setLastTempPasswordUser("");
    setSelectedUserId(null);
    setUserEdit(defaultUserEdit());
    setAgents([]);
    setRoles([]);
    setTools([]);
    setSchedulerItems([]);
    setScheduleForm(defaultSchedule());
    setScheduleNlRequest("");
    setSchedulerView("list");
    setChatInput("");
    const nextSessionId = makeId();
    sessionIdRef.current = nextSessionId;
    setChatSessionId(nextSessionId);
    setChatLines([]);
      setChatTraceLines([]);
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setPasswordMsg("");
    try {
      await changePassword(token, currentPassword, newPassword);
      const me = await getMe(token);
      setUser(me);
      setMustChangePassword(false);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordMsg("Password changed successfully.");
    } catch (err) {
      setPasswordMsg(err instanceof Error ? err.message : "Password change failed");
    }
  }

  async function loadSettingsData() {
    if (!token) return;
    try {
      const values = await getSettings(token);
      syncSettings(values);
      setSettingsMsg("Settings loaded.");
    } catch (err) {
      setSettingsMsg(err instanceof Error ? err.message : "Failed to load settings");
    }
  }

  async function saveSettingsPatch(values: Record<string, unknown>, okMsg: string): Promise<boolean> {
    if (!token) return false;
    try {
      const updated = await updateSettings(token, values);
      syncSettings(updated);
      setSettingsMsg(okMsg);
      return true;
    } catch (err) {
      setSettingsMsg(err instanceof Error ? err.message : "Failed to save settings");
      return false;
    }
  }

  async function saveSystemSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    const activityLevel = s("agent_activity_level", "full") === "partial" ? "partial" : "full";
    const dirs = accessibleDirsText
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean);
    const ok = await saveSettingsPatch(
      {
        sqlite_db_path: s("sqlite_db_path", "backend.db"),
        file_storage_path: s("file_storage_path", "storage/files"),
        debug_mode: b("debug_mode", false),
        agent_activity_level: activityLevel,
        agent_activity_partial_keep_steps: n("agent_activity_partial_keep_steps", 5),
        agent_activity_mode: activityLevel === "partial" ? "structured" : "fast",
        default_directory: s("default_directory", ""),
        accessible_directories: dirs,
      },
      "System settings saved.",
    );
    if (ok) showAlert("System settings saved.");
  }

  async function saveAiSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    const provider = s("llm_provider", "gemini").toLowerCase();
    const payload: Record<string, unknown> = {
      llm_provider: provider,
      embedding_model_name: "jinaai/jina-embeddings-v3",
    };

    if (provider === "gemini") {
      payload.gemini_api_key = s("gemini_api_key", "");
      payload.gemini_model = s("gemini_model", "gemini-2.5-flash");
      payload.gemini_temperature = n("gemini_temperature", 0);
    } else if (provider === "groq") {
      payload.groq_api_key = s("groq_api_key", "");
      payload.groq_model = s("groq_model", "llama-3.3-70b-versatile");
      payload.groq_temperature = n("groq_temperature", 1);
    } else if (provider === "local") {
      payload.local_llm_url = s("local_llm_url", "http://127.0.0.1:1234/v1");
      payload.local_llm_model = s("local_llm_model", "local-model");
    } else {
      payload.openrouter_api_key = s("openrouter_api_key", "");
      payload.openrouter_model = s("openrouter_model", "google/gemini-2.5-flash");
      payload.openrouter_temperature = n("openrouter_temperature", 0);
      payload.openrouter_top_p = n("openrouter_top_p", 1);
      payload.openrouter_seed = s("openrouter_seed", "");
      payload.openrouter_provider_order = s("openrouter_provider_order", "");
      payload.openrouter_allow_fallbacks = b("openrouter_allow_fallbacks", true);
      payload.openrouter_require_parameters = b("openrouter_require_parameters", false);
      payload.openrouter_include_reasoning = b("openrouter_include_reasoning", false);
    }

    const ok = await saveSettingsPatch(payload, `AI settings saved for ${provider} and applied to runtime.`);
    if (ok) {
      setAiRestartRequired(false);
      showAlert(`AI settings saved for ${provider}.`);
    }
  }

  async function saveTelegramSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    const ok = await saveSettingsPatch(
      {
        telegram_enabled: b("telegram_enabled", false),
        telegram_bot_token: s("telegram_bot_token", ""),
        telegram_poll_timeout: n("telegram_poll_timeout", 25),
        telegram_poll_retry_seconds: n("telegram_poll_retry_seconds", 2),
        telegram_test_chat_id: s("telegram_test_chat_id", ""),
        telegram_test_message: s("telegram_test_message", "Hello from Desktop Agentic System"),
      },
      "Telegram settings saved.",
    );
    if (ok) showAlert("Telegram settings saved.");
  }

  async function saveEmailSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    const ok = await saveSettingsPatch(
      {
        gmail_enabled: b("gmail_enabled", false),
        gmail_sender_email: s("gmail_sender_email", ""),
        gmail_sender_name: s("gmail_sender_name", ""),
        gmail_app_password: s("gmail_app_password", ""),
        gmail_test_to: s("gmail_test_to", ""),
        gmail_test_subject: s("gmail_test_subject", "Test Email from OASIS"),
        gmail_test_body: s("gmail_test_body", "Hello from OASIS"),
      },
      "Email settings saved.",
    );
    if (ok) showAlert("Email settings saved.");
  }

  async function saveWhatsAppSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    const ok = await saveSettingsPatch(
      {
        whatsapp_enabled: b("whatsapp_enabled", false),
        whatsapp_folder_root: s("whatsapp_folder_root", ""),
        whatsapp_poll_seconds: n("whatsapp_poll_seconds", 1),
        whatsapp_test_to: s("whatsapp_test_to", ""),
        whatsapp_test_message: s("whatsapp_test_message", "Hello from Desktop Agentic System"),
      },
      "Additional WhatsApp settings saved.",
    );
    if (ok) showAlert("WhatsApp settings saved.");
  }

  async function saveSchedulerSettings() {
    if (!isAdmin) { setSettingsMsg("Admin access required to change settings."); return; }
    await saveSettingsPatch(
      {
        scheduler_enabled: b("scheduler_enabled", false),
        scheduler_poll_minutes: n("scheduler_poll_minutes", 1),
      },
      "Scheduler settings saved.",
    );
  }

  async function loadHistoryList() {
    if (!token) return;
    setHistoryMsg("Loading history...");
    try {
      const res = await listHistory(token);
      setHistoryItems(res.items);
      if (res.items.length === 0) setHistoryDetail(null);
      setHistoryMsg(`Loaded ${res.count} items.`);
    } catch (err) {
      setHistoryMsg(err instanceof Error ? err.message : "Failed to load history");
    }
  }

  async function loadHistoryDetail(id: number) {
    if (!token) return;
    try {
      const res = await getHistory(token, id);
      setHistoryDetail(res);
      setHistoryMsg(`Loaded ${res.messages.length} messages.`);
    } catch (err) {
      setHistoryMsg(err instanceof Error ? err.message : "Failed to load chat history");
    }
  }

  async function continueHistoryChat() {
    if (!token || !historyDetail) return;
    const chatId = asNumber(historyDetail.history.id, 0);
    if (!chatId) {
      setHistoryMsg("Select a valid chat history item.");
      return;
    }
    try {
      const res = await resumeHistory(token, chatId);
      const nextSessionId = asString(res.session_id).trim();
      if (!nextSessionId) {
        throw new Error("History resume did not return a session ID");
      }
      sessionIdRef.current = nextSessionId;
      setChatSessionId(nextSessionId);
      setChatBusy(false);
      setChatInput("");
      setChatAttachment(null);
      setChatTraceLines([]);
      setChatLines(
        res.chat_lines.map((line) => ({
          id: makeId(),
          role: line.role === "user" ? "user" : "assistant",
          text: asString(line.text),
        })),
      );
      setMainTab("chat");
      setChatWorkspaceTab("messages");
      setHistoryMsg(`Chat #${chatId} loaded. Continue from the Chat tab.`);
    } catch (err) {
      setHistoryMsg(err instanceof Error ? err.message : "Failed to resume chat history");
    }
  }

  async function loadSessionsList() {
    if (!token) return;
    setSessionsMsg("Loading sessions...");
    try {
      const res = await listSessions(token);
      setSessions(res.items);
      setSessionsMsg(`Active sessions: ${res.count}`);
    } catch (err) {
      setSessionsMsg(err instanceof Error ? err.message : "Failed to load sessions");
    }
  }

  async function loadLogsList() {
    if (!token) return;
    setLogsMsg("Loading logs...");
    try {
      const res = await listLogs(token);
      setLogsMap(res.logs);
      const first = Object.keys(res.logs)[0] || "";
      setSelectedLog(first);
      setLogsMsg(first ? `Selected ${first}` : "No logs available.");
      if (first) await loadLogContent(first, logLines);
    } catch (err) {
      setLogsMsg(err instanceof Error ? err.message : "Failed to load logs");
    }
  }

  async function loadLogContent(name: string, lines: number) {
    if (!token || !name) return;
    try {
      const res = await readLog(token, name, lines);
      setLogContent(res.content || "");
      setLogsMsg(res.path ? `${name}: ${res.path}` : `${name}: file not found`);
    } catch (err) {
      setLogsMsg(err instanceof Error ? err.message : "Failed to read log");
    }
  }

  async function loadIntegrationsStatus() {
    if (!token) return;
    try {
      const res = await getIntegrationsStatus(token);
      setIntegrations(res);
      setIntegrationsMsg("Integration status refreshed.");
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to load integrations");
    }
  }

  async function loadServiceStatus() {
    if (!token) return;
    try {
      const res = await getServiceStatus(token);
      setServiceStatus(res);
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to load service status");
    }
  }
  async function loadWhatsAppHeadlessStatus(options?: { silent?: boolean }) {
    if (!token || !isAdmin) return;
    try {
      const payload = await getWhatsAppHeadlessStatus(token);
      const status = asRecord(payload.status);
      setWhatsAppHeadlessStatus(status);
      if (!asBool(payload.ok, true)) {
        const errText = asString(payload.error, "Failed to load headless WhatsApp status");
        setWhatsAppHeadlessMsg(errText);
      }
      const statusSettings = asRecord(status.settings);
      const baseFolder = asString(statusSettings.base_folder, "").trim();
      if (baseFolder) {
        setSettings((prev) => (prev.whatsapp_folder_root === baseFolder ? prev : { ...prev, whatsapp_folder_root: baseFolder }));
      }
      const register = asRecord(status.register);
      const knownPhone = asString(register.phone_number, "").trim();
      if (knownPhone) {
        setWhatsAppRegisterPhone((prev) => (prev.trim() ? prev : knownPhone));
      }
      const regStage = asString(register.stage, "").trim().toLowerCase();
      const regError = asString(register.last_error, "").trim();
      if (regStage === "error" && regError) {
        setWhatsAppHeadlessMsg(`Registration failed: ${regError}`);
      } else if (regStage === "linked") {
        setWhatsAppHeadlessMsg("WhatsApp number linked successfully.");
      } else if (!options?.silent && asBool(payload.ok, true)) {
        setWhatsAppHeadlessMsg("Headless WhatsApp status refreshed.");
      }
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to load headless WhatsApp status");
    }
  }

  async function startWhatsAppRegistrationFlow() {
    if (!token || !isAdmin) return;
    const phone = whatsappRegisterPhone.trim();
    const baseFolder = s("whatsapp_folder_root", "").trim();
    if (!phone) {
      setWhatsAppHeadlessMsg("Enter a WhatsApp number with country code.");
      return;
    }

    setWhatsAppHeadlessBusy("register_start");
    try {
      setWhatsAppHeadlessMsg("Starting WhatsApp registration service...");
      const payload = await startWhatsAppHeadlessRegister(token, phone, baseFolder);
      const status = asRecord(payload.status);
      setWhatsAppHeadlessStatus(status);
      if (asBool(payload.ok, false)) {
        setWhatsAppHeadlessMsg("Registration request accepted. Use the pairing code shown beside Register.");
      } else {
        setWhatsAppHeadlessMsg(asString(payload.error, "Failed to start registration"));
      }
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to start registration");
    } finally {
      setWhatsAppHeadlessBusy("");
    }
  }

  async function logoutWhatsAppLinkFlow() {
    if (!token || !isAdmin) return;
    setWhatsAppHeadlessBusy("register_logout");
    try {
      const payload = await logoutWhatsAppHeadless(token);
      setWhatsAppHeadlessStatus(asRecord(payload.status));
      setWhatsAppHeadlessMsg("WhatsApp link logged out. You can register again with a new number.");
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to logout WhatsApp link");
    } finally {
      setWhatsAppHeadlessBusy("");
    }
  }

  async function stopWhatsAppRegistrationFlow() {
    if (!token || !isAdmin) return;
    setWhatsAppHeadlessBusy("register_stop");
    try {
      const payload = await stopWhatsAppHeadlessRegister(token);
      setWhatsAppHeadlessStatus(asRecord(payload.status));
      setWhatsAppHeadlessMsg("WhatsApp registration stopped.");
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to stop registration");
    } finally {
      setWhatsAppHeadlessBusy("");
    }
  }

  async function startWhatsAppDaemonFlow() {
    if (!token || !isAdmin) return;
    const baseFolder = s("whatsapp_folder_root", "").trim();

    setWhatsAppHeadlessBusy("daemon_start");
    try {
      setWhatsAppHeadlessMsg("Starting WhatsApp daemon...");
      const payload = await startWhatsAppHeadlessDaemon(token, baseFolder);
      setWhatsAppHeadlessStatus(asRecord(payload.status));
      if (asBool(payload.ok, false)) {
        setWhatsAppHeadlessMsg("WhatsApp daemon started.");
      } else {
        setWhatsAppHeadlessMsg(asString(payload.error, "Failed to start daemon"));
      }
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to start daemon");
    } finally {
      setWhatsAppHeadlessBusy("");
    }
  }

  async function stopWhatsAppDaemonFlow() {
    if (!token || !isAdmin) return;
    setWhatsAppHeadlessBusy("daemon_stop");
    try {
      const payload = await stopWhatsAppHeadlessDaemon(token);
      setWhatsAppHeadlessStatus(asRecord(payload.status));
      setWhatsAppHeadlessMsg("WhatsApp daemon stopped.");
    } catch (err) {
      setWhatsAppHeadlessMsg(err instanceof Error ? err.message : "Failed to stop daemon");
    } finally {
      setWhatsAppHeadlessBusy("");
    }
  }

  async function doTelegramRestart() {
    if (!token || !isAdmin) return;
    try {
      setIntegrationsMsg("Restarting Telegram service...");
      const res = await restartTelegram(token);
      await loadIntegrationsStatus();
      setIntegrationsMsg(asBool(res.ok, true) ? "Telegram restart requested." : asString(res.error, "Failed to restart Telegram"));
      if (asBool(res.ok, false)) {
        setAiRestartRequired(false);
        showAlert("Telegram restart requested.");
      }
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to restart Telegram");
    }
  }

  async function doTelegramStop() {
    if (!token || !isAdmin) return;
    try {
      setIntegrationsMsg("Stopping Telegram service...");
      const res = await stopTelegram(token);
      await loadIntegrationsStatus();
      setIntegrationsMsg(asBool(res.ok, true) ? "Telegram stopped." : asString(res.error, "Failed to stop Telegram"));
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to stop Telegram");
    }
  }

  async function doTelegramTest() {
    if (!token || !isAdmin) return;
    try {
      const res = await testTelegram(token, s("telegram_test_chat_id", ""), s("telegram_test_message", ""));
      setIntegrationsMsg(`Telegram test: ${pretty(res)}`);
      if (asBool(res.ok, false)) showAlert("Telegram test message sent.");
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed Telegram test");
    }
  }

  async function doWhatsAppRestart() {
    if (!token || !isAdmin) return;
    try {
      const res = await restartWhatsApp(token);
      await loadIntegrationsStatus();
      setIntegrationsMsg(asBool(res.ok, true) ? "WhatsApp restart requested." : asString(res.error, "Failed to restart WhatsApp"));
      if (asBool(res.ok, false)) setAiRestartRequired(false);
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to restart WhatsApp");
    }
  }

  async function doWhatsAppStop() {
    if (!token || !isAdmin) return;
    try {
      const res = await stopWhatsApp(token);
      await loadIntegrationsStatus();
      setIntegrationsMsg(asBool(res.ok, true) ? "WhatsApp stopped." : asString(res.error, "Failed to stop WhatsApp"));
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed to stop WhatsApp");
    }
  }

  async function doWhatsAppTest() {
    if (!token || !isAdmin) return;
    try {
      const res = await testWhatsApp(token, s("whatsapp_test_to", ""), s("whatsapp_test_message", ""));
      setIntegrationsMsg(`WhatsApp test: ${pretty(res)}`);
      if (asBool(res.ok, false)) showAlert("WhatsApp test message sent.");
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : "Failed WhatsApp test");
    }
  }

  async function doEmailTest() {
    if (!token || !isAdmin) return;
    try {
      const res = await testEmail(
        token,
        s("gmail_test_to", ""),
        s("gmail_test_subject", "Test Email from OASIS"),
        s("gmail_test_body", "Hello from OASIS"),
      );
      setSettingsMsg(`Email test: ${pretty(res)}`);
      if (asBool(res.ok, false)) showAlert("Test email sent.");
    } catch (err) {
      setSettingsMsg(err instanceof Error ? err.message : "Failed to send test email");
    }
  }

  function serviceRunning(key: ServiceKey): boolean {
    return asBool(asRecord(serviceStatus[key]).running, false);
  }

  async function handleApiService(action: "stop" | "restart") {
    if (!token || !isAdmin) return;
    try {
      const res = action === "stop" ? await stopApiService(token) : await restartApiService(token);
      setIntegrationsMsg(asBool(res.ok, true) ? `API ${action} requested.` : asString(res.error, `Failed to ${action} API`));
      if (action === "restart") setAiRestartRequired(false);
      if (action === "stop") {
        setTimeout(() => {
          window.location.reload();
        }, 1200);
      }
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : `Failed to ${action} API`);
    }
  }

  async function handleWebUiService(action: "stop" | "restart") {
    if (!token || !isAdmin) return;
    try {
      const res = action === "stop" ? await stopWebUiService(token) : await restartWebUiService(token);
      setIntegrationsMsg(asBool(res.ok, true) ? `Web UI ${action} requested.` : asString(res.error, `Failed to ${action} Web UI`));
      if (action === "restart") {
        setAiRestartRequired(false);
        setTimeout(() => {
          window.location.reload();
        }, 1200);
      }
      if (action === "stop") {
        setTimeout(() => {
          window.location.reload();
        }, 1200);
      }
    } catch (err) {
      setIntegrationsMsg(err instanceof Error ? err.message : `Failed to ${action} Web UI`);
    }
  }

  async function loadUsersList(options?: { silent?: boolean }) {
    if (!token || !isAdmin) return;
    const silent = Boolean(options?.silent);
    if (!silent) {
      setUsersMsg("Loading users...");
    }
    try {
      const res = await listUsers(token);
      setUsers(res.users);
      setShiftLookupOptions(Array.isArray(res.shift_options) ? res.shift_options : []);
      setDepartmentLookupOptions(Array.isArray(res.department_options) ? res.department_options : []);
      if (!silent) {
        setUsersMsg(`Loaded ${res.count} users.`);
      }
    } catch (err) {
      if (!silent) {
        setUsersMsg(err instanceof Error ? err.message : "Failed to load users");
      }
    }
  }

  function selectUserForEdit(target: AdminUser) {
    setSelectedUserId(target.id);
    setUserEdit({
      username: asString(target.username),
      email: asString(target.email),
      mobile_number: asString(target.mobile_number),
      whatsapp_number: asString(target.whatsapp_number),
      telegram_chat_id: asString(target.telegram_chat_id),
      is_active: Boolean(target.is_active),
      is_admin: Boolean(target.is_admin),
      role_id: target.role_id === null || target.role_id === undefined ? "" : String(target.role_id),
      role: asString(target.role) || roleNameById.get(String(target.role_id ?? "")) || "",
      shift_id: target.shift_id === null || target.shift_id === undefined ? "" : String(target.shift_id),
      shift: asString(target.shift),
      department_id: target.department_id === null || target.department_id === undefined ? "" : String(target.department_id),
      department: asString(target.department),
    });
  }

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    if (!token || !isAdmin) return;
    try {
      const res = await createUser(token, {
        username: newUsername.trim(),
        email: newEmail.trim() || undefined,
        is_admin: newIsAdmin,
        mobile_number: newMobile.trim() || undefined,
        whatsapp_number: newWhatsApp.trim() || undefined,
        telegram_chat_id: newTelegram.trim() || undefined,
      });
      const generated = extractTemporaryPassword(res);
      if (generated) {
        const createdName = res.user?.username || newUsername.trim();
        setManualPasswordNotice(`User '${createdName}': ${generated}`);
        setUsersMsg(`Temporary password for '${createdName}': ${generated}`);
      } else {
        const warn = "API response did not include a temporary password. Restart API service and retry.";
        setManualPasswordNotice(warn);
        setUsersMsg(warn);
      }
      setNewUsername("");
      setNewEmail("");
      setNewIsAdmin(false);
      setNewMobile("");
      setNewWhatsApp("");
      setNewTelegram("");
      await loadUsersList({ silent: true });
    } catch (err) {
      setUsersMsg(err instanceof Error ? err.message : "Failed to create user");
    }
  }

  async function handleSaveUserEdit() {
    if (!token || !isAdmin || selectedUserId === null) return;
    const payload: Record<string, unknown> = {
      username: userEdit.username.trim(),
      email: userEdit.email.trim(),
      mobile_number: userEdit.mobile_number.trim(),
      whatsapp_number: userEdit.whatsapp_number.trim(),
      telegram_chat_id: userEdit.telegram_chat_id.trim(),
      is_active: userEdit.is_active,
      is_admin: userEdit.is_admin,
      role: userEdit.role.trim(),
      shift: userEdit.shift.trim(),
      department: userEdit.department.trim(),
    };
    payload.role_id = userEdit.role_id.trim() ? asNumber(userEdit.role_id, 0) : null;
    payload.shift_id = userEdit.shift_id.trim() ? asNumber(userEdit.shift_id, 0) : null;
    payload.department_id = userEdit.department_id.trim() ? asNumber(userEdit.department_id, 0) : null;

    setBusyAction("save-user");
    setUsersMsg("Saving user...");
    try {
      await updateUser(token, selectedUserId, payload);
      setUsersMsg(`Updated user #${selectedUserId}.`);
      await loadUsersList();
      showAlert(`User #${selectedUserId} saved.`);
    } catch (err) {
      setUsersMsg(err instanceof Error ? err.message : "Failed to update user");
    } finally {
      setBusyAction("");
    }
  }

  async function handleSetActiveUserContext() {
    if (!token || selectedUserId === null) return;
    const found = users.find((u) => u.id === selectedUserId);
    if (!found) return;
    setBusyAction("set-active-user");
    setUsersMsg("Setting active user...");
    try {
      const updated = await updateSettings(token, {
        current_user_id: found.id,
        current_username: found.username,
        current_user_email: found.email || "",
      });
      syncSettings(updated);
      setUsersMsg(`Active context set to ${found.username}.`);
      showAlert(`Active user set to ${found.username}.`);
    } catch (err) {
      setUsersMsg(err instanceof Error ? err.message : "Failed to set active context");
    } finally {
      setBusyAction("");
    }
  }

  async function handleSendNewPassword(userId: number) {
    if (!token || !isAdmin) {
      return;
    }

    setBusyAction("send-password");
    setUsersMsg("Resetting password...");
    setManualPasswordNotice("");
    setLastTempPassword("");
    setLastTempPasswordUser("");
    try {
      const res = await sendNewPassword(token, userId);
      const generated = extractTemporaryPassword(res);

      const targetUser = users.find((u) => u.id === userId);
      const targetName = targetUser?.username || `#${userId}`;
      if (generated) {
        setLastTempPassword(generated);
        setLastTempPasswordUser(targetName);
        setManualPasswordNotice(`Password generated for '${targetName}'. Copy it below.`);
        setUsersMsg(`Temporary password generated for '${targetName}'.`);
      } else {
        const warn = `Password reset completed for '${targetName}', but API did not return the generated password.`;
        setManualPasswordNotice(warn);
        setUsersMsg(warn);
      }
      await loadUsersList({ silent: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed password reset";
      setManualPasswordNotice(msg);
      setUsersMsg(msg);
    } finally {
      setBusyAction("");
    }
  }

  async function copyTemporaryPassword() {
    if (!lastTempPassword) return;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(lastTempPassword);
        setUsersMsg("Temporary password copied to clipboard.");
      } else {
        setUsersMsg("Clipboard is not available in this browser. Copy from the field manually.");
      }
    } catch {
      setUsersMsg("Failed to copy. Copy from the field manually.");
    }
  }

  async function loadAgentsList() {
    if (!token) return;
    setAgentsMsg("Loading agents...");
    try {
      const res = await listAgents(token);
      setAgents(res.items);
      setAgentsMsg(`Loaded ${res.count} agents.`);
    } catch (err) {
      setAgentsMsg(err instanceof Error ? err.message : "Failed to load agents");
    }
  }

  async function openAgent(name: string) {
    if (!token) return;
    try {
      const res = await getAgent(token, name);
      setAgentName(asString(res.agent.name));
      setAgentDescription(asString(res.agent.description));
      setAgentPrompt(asString(res.agent.prompt_content));
      setAgentActive(asNumber(res.agent.is_active, 1) === 1);
      setAgentToolsSelected(Array.isArray(res.agent.tools) ? res.agent.tools : []);
      setAgentVersions(res.versions || []);
      setAgentRestoreVersion("");
      setAgentsMsg(`Editing ${name}.`);
    } catch (err) {
      setAgentsMsg(err instanceof Error ? err.message : "Failed to load agent detail");
    }
  }

  function newAgentDraft() {
    setAgentName("");
    setAgentDescription("");
    setAgentPrompt("");
    setAgentActive(true);
    setAgentToolsSelected([]);
    setAgentVersions([]);
    setAgentRestoreVersion("");
  }

  function toggleAgentTool(toolName: string) {
    setAgentToolsSelected((prev) => (prev.includes(toolName) ? prev.filter((x) => x !== toolName) : [...prev, toolName]));
  }

  async function handleSaveAgent() {
    if (!token || !isAdmin) return;
    if (!agentName.trim() || !agentPrompt.trim()) {
      setAgentsMsg("Agent name and prompt are required.");
      return;
    }
    try {
      await saveAgent(token, {
        name: agentName.trim(),
        description: agentDescription.trim(),
        prompt_content: agentPrompt,
        is_active: agentActive,
        tools: agentToolsSelected,
      });
      setAgentsMsg(`Saved ${agentName.trim()}.`);
      await loadAgentsList();
      await openAgent(agentName.trim());
      showAlert(`Agent ${agentName.trim()} saved.`);
    } catch (err) {
      setAgentsMsg(err instanceof Error ? err.message : "Failed to save agent");
    }
  }

  async function handleRestoreAgent() {
    if (!token || !isAdmin || !agentName.trim() || !agentRestoreVersion.trim()) return;
    const version = asNumber(agentRestoreVersion, 0);
    if (version <= 0) {
      setAgentsMsg("Invalid version.");
      return;
    }
    try {
      await restoreAgent(token, agentName.trim(), version);
      setAgentsMsg(`Restored ${agentName.trim()} from version ${version}.`);
      await loadAgentsList();
      await openAgent(agentName.trim());
      showAlert(`Agent ${agentName.trim()} restored from version ${version}.`);
    } catch (err) {
      setAgentsMsg(err instanceof Error ? err.message : "Failed to restore version");
    }
  }

  async function loadRolesList() {
    if (!token) return;
    setRolesMsg("Loading roles...");
    try {
      const res = await listRoles(token);
      setRoles(res.items);
      setRolesMsg(`Loaded ${res.count} roles.`);
    } catch (err) {
      setRolesMsg(err instanceof Error ? err.message : "Failed to load roles");
    }
  }

  function openRole(role: RoleItem) {
    setRoleId(role.id);
    setRoleName(asString(role.name));
    setRoleDescription(asString(role.description));
    setRoleAgentsSelected(Array.isArray(role.agents) ? role.agents : []);
  }

  function newRoleDraft() {
    setRoleId(null);
    setRoleName("");
    setRoleDescription("");
    setRoleAgentsSelected([]);
  }

  function toggleRoleAgent(agentNameValue: string) {
    setRoleAgentsSelected((prev) => (prev.includes(agentNameValue) ? prev.filter((x) => x !== agentNameValue) : [...prev, agentNameValue]));
  }

  async function handleSaveRole() {
    if (!token || !isAdmin) return;
    if (!roleName.trim()) {
      setRolesMsg("Role name is required.");
      return;
    }
    setBusyAction("save-role");
    setRolesMsg("Saving role...");
    try {
      await saveRole(token, { name: roleName.trim(), description: roleDescription.trim(), agent_names: roleAgentsSelected });
      setRolesMsg(`Saved role ${roleName.trim()}.`);
      await loadRolesList();
      showAlert(`Role ${roleName.trim()} saved.`);
    } catch (err) {
      setRolesMsg(err instanceof Error ? err.message : "Failed to save role");
    } finally {
      setBusyAction("");
    }
  }

  async function handleDeleteRole() {
    if (!token || !isAdmin || roleId === null) return;
    setBusyAction("delete-role");
    setRolesMsg("Deleting role...");
    try {
      await deleteRole(token, roleId);
      setRolesMsg(`Deleted role #${roleId}.`);
      newRoleDraft();
      await loadRolesList();
      showAlert(`Role #${roleId} deleted.`);
    } catch (err) {
      setRolesMsg(err instanceof Error ? err.message : "Failed to delete role");
    } finally {
      setBusyAction("");
    }
  }

  async function loadToolsList() {
    if (!token) return;
    setToolsMsg("Loading tools...");
    try {
      const res = await listTools(token);
      setTools(res.items);
      if (res.items.length > 0 && !selectedToolName) {
        setSelectedToolName(res.items[0].name);
        setToolDescriptionDraft(res.items[0].description || "");
      }
      setToolsMsg(`Loaded ${res.count} tools.`);
    } catch (err) {
      setToolsMsg(err instanceof Error ? err.message : "Failed to load tools");
    }
  }

  function selectTool(name: string) {
    setSelectedToolName(name);
    const found = tools.find((t) => t.name === name);
    setToolDescriptionDraft(found?.description || "");
  }

  async function handleRefreshToolRegistry() {
    if (!token || !isAdmin) return;
    try {
      const res = await refreshTools(token);
      setToolsMsg(`Tool registry refreshed: ${pretty(res)}`);
      await loadToolsList();
    } catch (err) {
      setToolsMsg(err instanceof Error ? err.message : "Failed to refresh registry");
    }
  }

  async function handleSaveToolDescription() {
    if (!token || !isAdmin || !selectedToolName) return;
    try {
      await updateToolDescription(token, selectedToolName, toolDescriptionDraft);
      setToolsMsg(`Updated ${selectedToolName}.`);
      await loadToolsList();
      showAlert(`Tool ${selectedToolName} saved.`);
    } catch (err) {
      setToolsMsg(err instanceof Error ? err.message : "Failed to save description");
    }
  }

  async function loadSchedulerStatus() {
    if (!token) return;
    try {
      const res = await getSchedulerStatus(token);
      setSchedulerStatus(res);
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to load scheduler status");
    }
  }

  async function loadSchedulesList() {
    if (!token) return;
    try {
      const res = await listSchedules(token);
      setSchedulerItems(res.items);
      setSchedulerMsg(`Loaded ${res.count} schedules.`);
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to load schedules");
    }
  }

  function openSchedule(item: SchedulerItem) {
    const raw = item as unknown as Record<string, unknown>;
    setScheduleForm({
      id: asNumber(raw.id, 0),
      title: asString(raw.title),
      task_prompt: asString(raw.task_prompt),
      schedule_type: asString(raw.schedule_type, "other"),
      interval_minutes: asNumber(raw.interval_minutes, 0),
      run_hour: asNumber(raw.run_hour, 9),
      run_minute: asNumber(raw.run_minute, 0),
      run_day_of_week: asNumber(raw.run_day_of_week, 0),
      run_day_of_month: asNumber(raw.run_day_of_month, 1),
      timezone: asString(raw.timezone, "Asia/Calcutta"),
      is_enabled: asBool(raw.is_enabled, true),
      last_run_at: asString(raw.last_run_at),
      last_result: asString(raw.last_result),
    });
    setScheduleNlRequest(asString(raw.nl_request));
    setSchedulerView("editor");
  }

  function newScheduleDraft() {
    setScheduleForm(defaultSchedule());
    setScheduleNlRequest("");
    setSchedulerView("create");
  }

  async function handleValidateSchedule() {
    if (!token || !scheduleNlRequest.trim()) return;
    try {
      const parsed = await validateSchedule(token, scheduleNlRequest.trim());
      if (!asBool(parsed.is_valid, false)) {
        setSchedulerMsg(`Invalid schedule: ${asString(parsed.reason, "Unknown")}`);
        return;
      }
      setScheduleForm((prev) => ({
        ...prev,
        title: asString(parsed.title, prev.title || "Scheduled Task"),
        task_prompt: asString(parsed.task_prompt, prev.task_prompt),
        schedule_type: asString(parsed.schedule_type, prev.schedule_type),
        interval_minutes: asNumber(parsed.interval_minutes, prev.interval_minutes),
        run_hour: asNumber(parsed.run_hour, prev.run_hour),
        run_minute: asNumber(parsed.run_minute, prev.run_minute),
        run_day_of_week: asNumber(parsed.run_day_of_week, prev.run_day_of_week),
        run_day_of_month: asNumber(parsed.run_day_of_month, prev.run_day_of_month),
      }));
      setSchedulerMsg("Schedule request validated.");
      setSchedulerView("editor");
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to validate schedule");
    }
  }

  async function handleSaveSchedule() {
    if (!token || !isAdmin) return;
    const payload = {
      title: scheduleForm.title.trim() || "Scheduled Task",
      task_prompt: scheduleForm.task_prompt.trim(),
      schedule_type: scheduleForm.schedule_type.trim().toLowerCase() || "other",
      interval_minutes: scheduleForm.interval_minutes,
      run_hour: scheduleForm.run_hour,
      run_minute: scheduleForm.run_minute,
      run_day_of_week: scheduleForm.run_day_of_week,
      run_day_of_month: scheduleForm.run_day_of_month,
      timezone: scheduleForm.timezone.trim() || "Asia/Calcutta",
      is_enabled: scheduleForm.is_enabled,
    };
    if (!payload.task_prompt) {
      setSchedulerMsg("Task prompt is required.");
      return;
    }

    try {
      if (scheduleForm.id && scheduleForm.id > 0) {
        await updateSchedule(token, scheduleForm.id, payload);
        setSchedulerMsg(`Updated schedule #${scheduleForm.id}.`);
      } else {
        await createSchedule(token, payload);
        setSchedulerMsg("Schedule created.");
      }
      await loadSchedulesList();
      setSchedulerView("list");
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to save schedule");
    }
  }

  async function handleDeleteSchedule(id: number) {
    if (!token || !isAdmin) return;
    try {
      await deleteSchedule(token, id);
      setSchedulerMsg(`Deleted schedule #${id}.`);
      if (scheduleForm.id === id) newScheduleDraft();
      await loadSchedulesList();
      setSchedulerView("list");
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to delete schedule");
    }
  }

  async function handleRunSchedule(id: number) {
    if (!token || !isAdmin) return;
    try {
      const res = await runScheduleNow(token, id);
      setSchedulerMsg(`Run result: ${pretty(res)}`);
      await loadSchedulesList();
      setSchedulerView("list");
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to run schedule");
    }
  }

  async function handleRestartScheduler() {
    if (!token || !isAdmin) return;
    try {
      const res = await restartScheduler(token);
      setSchedulerMsg(asBool(res.ok, true) ? `Scheduler restart: ${pretty(res)}` : asString(res.error, "Failed to restart scheduler"));
      if (asBool(res.ok, false)) setAiRestartRequired(false);
      await loadSchedulerStatus();
      await loadIntegrationsStatus();
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to restart scheduler");
    }
  }

  async function handleStopScheduler() {
    if (!token || !isAdmin) return;
    try {
      const res = await stopScheduler(token);
      setSchedulerMsg(asBool(res.ok, true) ? "Scheduler stopped." : asString(res.error, "Failed to stop scheduler"));
      await loadSchedulerStatus();
      await loadIntegrationsStatus();
    } catch (err) {
      setSchedulerMsg(err instanceof Error ? err.message : "Failed to stop scheduler");
    }
  }

  async function handleAttachFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setChatAttachBusy(true);
    try {
      const base64 = await fileToBase64(file);
      setChatAttachment({
        filename: file.name || "attachment.bin",
        mime_type: file.type || "application/octet-stream",
        size_bytes: file.size || 0,
        data_base64: base64,
      });
    } catch (err) {
      setChatLines((prev) => [...prev, { id: makeId(), role: "error", text: err instanceof Error ? err.message : "Failed to attach file" }]);
    } finally {
      setChatAttachBusy(false);
    }
  }

  function clearAttachment() {
    setChatAttachment(null);
  }

  function openAttachPicker() {
    if (chatBusy || chatAttachBusy) return;
    chatFileInputRef.current?.click();
  }

  function sendChat() {
    if (!chatConnected || !token) {
      setChatLines((prev) => [...prev, { id: makeId(), role: "error", text: "Chat service not available" }]);
      return;
    }
    const msg = chatInput.trim();
    if (!msg && !chatAttachment) return;

    const filesPayload = chatAttachment ? [chatAttachment] : [];
    const composedUserText = [msg, chatAttachment ? `[Attached: ${chatAttachment.filename}]` : ""].filter(Boolean).join("\n");

    setChatLines((prev) => [...prev, { id: makeId(), role: "user", text: composedUserText || "(attachment)" }]);
    setChatBusy(true);
    setChatInput("");
    setChatAttachment(null);
    setChatTraceLines([]);

    void sendWebChat(token, { session_id: sessionIdRef.current, message: msg, files: filesPayload })
      .then(async (res) => {
        const requestId = asString(res.request_id).trim();
        if (!requestId) {
          throw new Error("Chat request id missing");
        }
        activeChatRequestRef.current = requestId;
        let seenUi = 0;
        let seenTrace = 0;

        while (activeChatRequestRef.current === requestId) {
          const snap = await getWebChatStatus(token, requestId);
          const uiFeedback = Array.isArray(snap.ui_feedback) ? snap.ui_feedback : [];
          const traceItems = Array.isArray(snap.trace) ? snap.trace : [];

          if (uiFeedback.length > seenUi) {
            const nextItems = uiFeedback.slice(seenUi);
            setChatLines((prev) => {
              const next = [...prev];
              for (const item of nextItems) {
                if (!item || typeof item !== "object") continue;
                const feedback = item as Record<string, unknown>;
                const message = asString(feedback.message).trim();
                const hint = asString(feedback.progress_hint).trim();
                if (!message && !hint) continue;
                next.push({
                  id: makeId(),
                  role: "status",
                  text: composeStatusText(asString(feedback.status, "working"), message, hint),
                });
              }
              return next;
            });
            seenUi = uiFeedback.length;
          }

          if (traceItems.length !== seenTrace) {
            setChatTraceLines(
              traceItems.map((item) => ({
                id: makeId(),
                eventType: asString(asRecord(item).eventType, "trace"),
                text: pretty(asRecord(item).payload),
              })),
            );
            seenTrace = traceItems.length;
          }

          if (snap.done) {
            const replyText = asString(snap.content).trim();
            if (replyText) {
              setChatLines((prev) => [...prev, { id: makeId(), role: "assistant", text: replyText }]);
            }
            break;
          }

          await new Promise((resolve) => window.setTimeout(resolve, 700));
        }
      })
      .catch((err) => {
        setChatLines((prev) => [...prev, { id: makeId(), role: "error", text: err instanceof Error ? err.message : "Chat failed" }]);
      })
      .finally(() => {
        activeChatRequestRef.current = "";
        setChatBusy(false);
      });
  }

  function stopChat() {
    if (!token) return;
    activeChatRequestRef.current = "";
    void stopWebChat(token, sessionIdRef.current).catch(() => {});
    setChatBusy(false);
  }

  function startNewSession() {
    if (chatBusy && token) {
      void stopWebChat(token, sessionIdRef.current).catch(() => {});
    }

    const nextSessionId = makeId();
    sessionIdRef.current = nextSessionId;
    setChatSessionId(nextSessionId);
    setChatBusy(false);
    setChatInput("");
    setChatAttachment(null);
    setChatLines([]);
    setChatTraceLines([]);
    activeChatRequestRef.current = "";
    setChatLines([{ id: makeId(), role: "status", text: composeStatusText("working", "New session started.") }]);
  }

  const selectedTool = tools.find((t) => t.name === selectedToolName) || null;
  const selectedAiProvider = s("llm_provider", "gemini").toLowerCase();
  const openrouterModelValue = s("openrouter_model", "google/gemini-2.5-flash");
  const selectedOpenRouterPreset = OPENROUTER_MODELS.some((model) => model.id === openrouterModelValue)
    ? openrouterModelValue
    : "";
  const roleNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const role of roles) {
      map.set(String(role.id), asString(role.name));
    }
    return map;
  }, [roles]);
  const shiftOptions = useMemo(
    () => {
      const lookup = shiftLookupOptions.map((item) => asString(item.name));
      return uniqueOptions(lookup, SHIFT_OPTIONS, users.map((item) => asString(item.shift)));
    },
    [shiftLookupOptions, users],
  );
  const departmentOptions = useMemo(
    () => {
      const lookup = departmentLookupOptions.map((item) => asString(item.name));
      return uniqueOptions(lookup, DEPARTMENT_OPTIONS, users.map((item) => asString(item.department)));
    },
    [departmentLookupOptions, users],
  );
  const whatsappHeadless = asRecord(whatsappHeadlessStatus);
  const whatsappNode = asRecord(whatsappHeadless.node);
  const whatsappScripts = asRecord(whatsappHeadless.scripts);
  const whatsappBridgeSettings = asRecord(whatsappHeadless.settings);
  const whatsappRegisterState = asRecord(whatsappHeadless.register);
  const whatsappDaemonState = asRecord(whatsappHeadless.daemon);
  const whatsappLegacyState = asRecord(integrations?.whatsapp);
  const whatsappPairingCode = asString(whatsappRegisterState.pairing_code, "").trim();
  const whatsappRegisterLogs = asStringArray(whatsappRegisterState.logs_tail).join("\n");
  const whatsappDaemonLogs = asStringArray(whatsappDaemonState.logs_tail).join("\n");
  const whatsappRegisterRunning = asBool(whatsappRegisterState.running, false);
  const whatsappDaemonRunning = asBool(whatsappDaemonState.running, false);
  const whatsappRegisterStage = asString(whatsappRegisterState.stage, "").trim().toLowerCase();
  const whatsappNodeAvailable = asBool(whatsappNode.available, false);
  const whatsappRegisterExists = asBool(whatsappScripts.register_exists, false);
  const whatsappDaemonExists = asBool(whatsappScripts.daemon_exists, false);
  const whatsappRegisterExeExists = asBool(whatsappScripts.register_exe_exists, false);
  const whatsappDaemonExeExists = asBool(whatsappScripts.daemon_exe_exists, false);
  const whatsappPackagedBridge = asBool(whatsappNode.packaged_windows_bridge, false);
  const whatsappAuthLinked = asBool(whatsappHeadless.auth_session_exists, false);
  const whatsappRegistrationStoppable = whatsappRegisterRunning || whatsappAuthLinked || whatsappRegisterStage === "linked";
  const whatsappLegacyRunning = asBool(whatsappLegacyState.running, false);
  const whatsappHeadlessReady = whatsappNodeAvailable && (whatsappPackagedBridge || (whatsappRegisterExists && whatsappDaemonExists));
  const storageRoot = s("file_storage_path", "storage/files").trim() || "storage/files";
  const configuredBridgeFolder = asString(whatsappBridgeSettings.configured_base_folder, "").trim();
  const fileBridgeFolder = asString(whatsappBridgeSettings.file_base_folder, "").trim();
  const activeBridgeFolder = asString(whatsappBridgeSettings.base_folder, "").trim();
  const telegramState = asRecord(integrations?.telegram);
  const telegramRunning = asBool(telegramState.running, false);
  const telegramEnabled = asBool(telegramState.enabled, false);
  const telegramHasToken = asBool(telegramState.has_token, false);
  const telegramStage = asString(telegramState.stage, "").trim() || (telegramRunning ? "running" : "stopped");
  const telegramStatusMessage = asString(telegramState.status_message, "").trim();
  const telegramLastError = asString(telegramState.last_error, "").trim();
  const whatsappRegisterError = asString(whatsappRegisterState.last_error, "").trim();
  const whatsappDaemonError = asString(whatsappDaemonState.last_error, "").trim();

  if (booting) return <div className="center-panel">Loading...</div>;

  if (!token || !user) {
    return (
      <div className="center-panel">
        <form className="card form-card" onSubmit={handleLogin} autoComplete="off">
          <div className="brand-head">
            <img src="/oasis-logo.png" alt="OASIS" className="brand-logo" />
            <h1>OASIS Web Access</h1>
          </div>
          <p className="muted">API: {apiBase}</p>
          <label>
            Login
            <input value={loginId} onChange={(e) => setLoginId(e.target.value)} placeholder="username or email" autoComplete="off" />
          </label>
          <label>
            Password
            <input type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} autoComplete="off" />
          </label>
          <button type="submit">Sign In</button>
          {authError && <div className="error-box">{authError}</div>}
        </form>
      </div>
    );
  }

  if (mustChangePassword) {
    return (
      <div className="center-panel">
        <form className="card form-card" onSubmit={handleChangePassword} autoComplete="off">
          <h1>Password Update Required</h1>
          <p className="muted">Change your temporary password before using OASIS.</p>
          <label>
            Current Password
            <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoComplete="current-password" />
          </label>
          <label>
            New Password
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" />
          </label>
          <button type="submit">Change Password</button>
          {passwordMsg && <div className="info-box">{passwordMsg}</div>}
          <button type="button" className="ghost" onClick={handleLogout}>
            Sign Out
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img src="/oasis-logo.png" alt="OASIS" className="sidebar-logo" />
          <h2>OASIS</h2>
          <p className="sidebar-version">{APP_VERSION}</p>
          <p className="muted small">{user.username}</p>
          <p className="muted small">{user.email || "(no email)"}</p>
        </div>
        <nav>
          {MAIN_TABS.map((tab) => (
            <button key={tab.id} className={mainTab === tab.id ? "active" : ""} onClick={() => setMainTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </nav>
        <button className="ghost" onClick={handleLogout}>
          Sign Out
        </button>
      </aside>

      <main className="main-panel">
        {mainTab === "chat" && (
          <section className="panel card">
            <div className="panel-head">
              <h3>Chat</h3>
              <div className="row">
                <span className={chatConnected ? "status ok" : "status bad"}>{chatConnected ? "Connected" : "Disconnected"}</span>
                <button className="ghost" onClick={startNewSession}>New Session</button>
              </div>
            </div>
            <p className="muted small">Session: <code>{chatSessionId}</code></p>
            <div className="subtab-row">
              <button className={chatWorkspaceTab === "messages" ? "active" : ""} onClick={() => setChatWorkspaceTab("messages")}>Messages</button>
              <button className={chatWorkspaceTab === "trace" ? "active" : ""} onClick={() => setChatWorkspaceTab("trace")}>Runtime Trace</button>
            </div>
            {chatWorkspaceTab === "messages" ? (
              <div className="chat-log" ref={chatLogRef}>
                {chatLines.map((line) => (
                  <ChatMessage key={line.id} role={line.role} text={line.text} />
                ))}
              </div>
            ) : (
              <div className="trace-log">
                {chatTraceLines.length === 0 ? (
                  <p className="muted">No runtime trace events yet.</p>
                ) : (
                  chatTraceLines.map((line) => (
                    <div key={line.id} className="trace-line">
                      <strong>{line.eventType}</strong>
                      <pre>{line.text}</pre>
                    </div>
                  ))
                )}
              </div>
            )}
            <div className="chat-controls">
              <input
                ref={chatFileInputRef}
                type="file"
                onChange={handleAttachFileChange}
                style={{ display: "none" }}
              />
              {chatAttachment && (
                <div className="chat-attachment-pill">
                  <div className="chat-attachment-meta">
                    <strong>{chatAttachment.filename}</strong>
                    <span className="muted small">{Math.max(1, Math.round(chatAttachment.size_bytes / 1024))} KB</span>
                  </div>
                  <button type="button" className="ghost" onClick={clearAttachment} disabled={chatBusy}>Remove</button>
                </div>
              )}
              <textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)} rows={3} placeholder="Type message..." />
              <div className="row">
                <button className="ghost" onClick={openAttachPicker} disabled={chatBusy || chatAttachBusy}>
                  {chatAttachBusy ? "Attaching..." : "Attach"}
                </button>
                <button onClick={sendChat} disabled={chatBusy || (!chatInput.trim() && !chatAttachment)}>Send</button>
                <button className="ghost" onClick={stopChat}>Stop</button>
              </div>
            </div>
          </section>
        )}

        {mainTab === "history" && (
          <section className="panel card">
            <div className="panel-head">
              <h3>History</h3>
              <div className="row">
                <button className="ghost" onClick={() => void loadHistoryList()}>Refresh</button>
                <button onClick={() => void continueHistoryChat()} disabled={!historyDetail}>Continue Chat</button>
              </div>
            </div>
            <div className="split-grid">
              <div className="list-panel">
                {historyItems.map((item) => (
                  <button key={item.id} className="list-item" onClick={() => void loadHistoryDetail(item.id)}>
                    <strong>{item.title || `Chat #${item.id}`}</strong>
                    <span className="muted small">{item.created_at} {item.interface ? `[${item.interface}]` : ""}</span>
                  </button>
                ))}
                {historyItems.length === 0 && <p className="muted">No history found.</p>}
              </div>
              <div className="detail-panel">
                {historyDetail ? (
                  <div className="chat-log">
                    {historyDetail.messages.map((m) => (
                      <div key={m.id} className={`chat-line ${m.role.toLowerCase() === "user" ? "user" : "assistant"}`}>
                        <strong>{m.role}</strong>
                        <ChatMessage role={m.role.toLowerCase() === "user" ? "user" : "assistant"} text={m.content} />
                        <small className="muted">{m.timestamp}</small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">Select a history item.</p>
                )}
              </div>
            </div>
            {historyMsg && <div className="info-box">{historyMsg}</div>}
          </section>
        )}

        {mainTab === "sessions" && (
          <section className="panel card">
            <div className="panel-head">
              <h3>Active Sessions</h3>
              <button className="ghost" onClick={() => void loadSessionsList()}>Refresh</button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Channel</th>
                    <th>Session</th>
                    <th>Idle</th>
                    <th>Last Message</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((sItem) => (
                    <tr key={`${sItem.channel}-${sItem.session_id}`}>
                      <td>{sItem.user || sItem.user_id}</td>
                      <td>{sItem.channel}</td>
                      <td>{sItem.session_id}</td>
                      <td>{sItem.idle_seconds}</td>
                      <td>{sItem.last_message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sessions.length === 0 && <p className="muted table-empty">No sessions.</p>}
            </div>
            {sessionsMsg && <div className="info-box">{sessionsMsg}</div>}
          </section>
        )}

        {mainTab === "logs" && (
          <section className="panel card">
            <div className="panel-head">
              <h3>System Logs</h3>
              <div className="row">
                <label className="inline-field">
                  Lines
                  <input type="number" min={10} max={2000} value={logLines} onChange={(e) => setLogLines(asNumber(e.target.value, 250))} />
                </label>
                <button className="ghost" onClick={() => void loadLogsList()}>Refresh Logs</button>
                <button onClick={() => void loadLogContent(selectedLog, logLines)} disabled={!selectedLog}>Read</button>
              </div>
            </div>
            <div className="split-grid">
              <div className="list-panel">
                {Object.entries(logsMap).map(([name, path]) => (
                  <button key={name} className={`list-item ${selectedLog === name ? "active" : ""}`} onClick={() => setSelectedLog(name)}>
                    <strong>{name}</strong>
                    <span className="muted small">{path || "(not found)"}</span>
                  </button>
                ))}
              </div>
              <div className="detail-panel">
                <textarea className="json-editor" value={logContent} readOnly />
              </div>
            </div>
            {logsMsg && <div className="info-box">{logsMsg}</div>}
          </section>
        )}

        {mainTab === "settings" && (
          <section className="panel card settings-shell">
            <div className="panel-head settings-shell-head">
              <h3>Settings</h3>
              <button className="ghost" onClick={() => void loadSettingsData()}>Reload Settings</button>
            </div>
            <div className="subtab-row settings-shell-tabs">
              {SETTINGS_TABS.map((tab) => (
                <button key={tab.id} className={settingsTab === tab.id ? "active" : ""} onClick={() => setSettingsTab(tab.id)}>
                  {tab.label}
                </button>
              ))}
            </div>
            {!isAdmin && <div className="info-box">Settings are view-only for non-admin users.</div>}

            {settingsTab === "system" && (
              <div className="tab-content">
                <div className="form-grid two-col">
                  <label>SQLite DB Path<input value={s("sqlite_db_path", "backend.db")} onChange={(e) => setSettingValue("sqlite_db_path", e.target.value)} /></label>
                  <label>File Storage Path<input value={s("file_storage_path", "storage/files")} onChange={(e) => setSettingValue("file_storage_path", e.target.value)} /></label>
                  <label>Default Directory<input value={s("default_directory", "")} onChange={(e) => setSettingValue("default_directory", e.target.value)} /></label>
                  <label>Activity Level
                    <select value={s("agent_activity_level", "full")} onChange={(e) => setSettingValue("agent_activity_level", e.target.value)}>
                      <option value="full">Full</option>
                      <option value="partial">Partial</option>
                    </select>
                  </label>
                  <label>Partial Keep Steps<input type="number" min={1} max={200} value={n("agent_activity_partial_keep_steps", 5)} onChange={(e) => setSettingValue("agent_activity_partial_keep_steps", asNumber(e.target.value, 5))} /></label>
                  <label className="check-label"><input type="checkbox" checked={b("debug_mode", false)} onChange={(e) => setSettingValue("debug_mode", e.target.checked)} />Enable debug approvals</label>
                </div>
                <label>Whitelisted Directories (one per line)
                  <textarea className="json-editor short" value={accessibleDirsText} onChange={(e) => setAccessibleDirsText(e.target.value)} />
                </label>
                <button onClick={() => void saveSystemSettings()} disabled={!isAdmin}>Save System Settings</button>
              </div>
            )}

            {settingsTab === "ai" && (
              <div className="tab-content ai-config-content">
                <div className="form-grid two-col">
                  <label>Provider
                    <select value={selectedAiProvider} onChange={(e) => setSettingValue("llm_provider", e.target.value)}>
                      <option value="gemini">Google Gemini</option>
                      <option value="groq">Groq</option>
                      <option value="local">Local LLM (LM Studio/Ollama)</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                  </label>
                </div>

                {selectedAiProvider === "gemini" && (
                  <div className="ai-provider-card">
                    <h4>Google Gemini Settings</h4>
                    <div className="form-grid two-col">
                      <label>Gemini API Key
                        <input type="password" value={s("gemini_api_key", "")} onChange={(e) => setSettingValue("gemini_api_key", e.target.value)} />
                      </label>
                      <label>Gemini Model
                        <input list="gemini-model-options" value={s("gemini_model", "gemini-2.5-flash")} onChange={(e) => setSettingValue("gemini_model", e.target.value)} />
                        <datalist id="gemini-model-options">
                          {GEMINI_MODELS.map((model) => <option key={model} value={model} />)}
                        </datalist>
                      </label>
                      <label>Gemini Temperature
                        <input type="number" min={0} max={2} step={0.1} value={n("gemini_temperature", 0)} onChange={(e) => setSettingValue("gemini_temperature", asNumber(e.target.value, 0))} />
                      </label>
                    </div>
                  </div>
                )}

                {selectedAiProvider === "groq" && (
                  <div className="ai-provider-card">
                    <h4>Groq Settings</h4>
                    <div className="form-grid two-col">
                      <label>Groq API Key
                        <input type="password" value={s("groq_api_key", "")} onChange={(e) => setSettingValue("groq_api_key", e.target.value)} />
                      </label>
                      <label>Groq Model
                        <input list="groq-model-options" value={s("groq_model", "llama-3.3-70b-versatile")} onChange={(e) => setSettingValue("groq_model", e.target.value)} />
                        <datalist id="groq-model-options">
                          {GROQ_MODELS.map((model) => <option key={model} value={model} />)}
                        </datalist>
                      </label>
                      <label>Groq Temperature
                        <input type="number" min={0} max={2} step={0.1} value={n("groq_temperature", 1)} onChange={(e) => setSettingValue("groq_temperature", asNumber(e.target.value, 1))} />
                      </label>
                    </div>
                  </div>
                )}

                {selectedAiProvider === "local" && (
                  <div className="ai-provider-card">
                    <h4>Local LLM Settings</h4>
                    <div className="form-grid two-col">
                      <label>Local URL
                        <input value={s("local_llm_url", "http://127.0.0.1:1234/v1")} onChange={(e) => setSettingValue("local_llm_url", e.target.value)} />
                      </label>
                      <label>Local Model
                        <input list="local-model-options" value={s("local_llm_model", "local-model")} onChange={(e) => setSettingValue("local_llm_model", e.target.value)} />
                        <datalist id="local-model-options">
                          {LOCAL_MODELS.map((model) => <option key={model} value={model} />)}
                        </datalist>
                      </label>
                    </div>
                  </div>
                )}

                {selectedAiProvider === "openrouter" && (
                  <div className="ai-provider-card">
                    <h4>OpenRouter Settings</h4>
                    <div className="openrouter-main-grid">
                      <label>OpenRouter API Key
                        <input type="password" value={s("openrouter_api_key", "")} onChange={(e) => setSettingValue("openrouter_api_key", e.target.value)} />
                      </label>
                      <label>OpenRouter Model
                        <select value={selectedOpenRouterPreset} onChange={(e) => e.target.value && setSettingValue("openrouter_model", e.target.value)}>
                          <option value="">Custom model ID</option>
                          {OPENROUTER_MODELS.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
                        </select>
                        <input value={openrouterModelValue} onChange={(e) => setSettingValue("openrouter_model", e.target.value)} placeholder="OpenRouter model ID" />
                        <span className="muted small">Pick a preset with comments or type any OpenRouter model ID.</span>
                      </label>
                    </div>
                    <details className="advanced-settings">
                      <summary>Advanced options</summary>
                      <div className="openrouter-advanced-grid">
                        <label>Temperature
                          <input type="number" min={0} max={2} step={0.1} value={n("openrouter_temperature", 0)} onChange={(e) => setSettingValue("openrouter_temperature", asNumber(e.target.value, 0))} />
                        </label>
                        <label>Top P
                          <input type="number" min={0.01} max={1} step={0.01} value={n("openrouter_top_p", 1)} onChange={(e) => setSettingValue("openrouter_top_p", asNumber(e.target.value, 1))} />
                        </label>
                        <label>Seed
                          <input value={s("openrouter_seed", "")} placeholder="Default random" onChange={(e) => setSettingValue("openrouter_seed", e.target.value)} />
                        </label>
                        <label>Provider Order
                          <input value={s("openrouter_provider_order", "")} placeholder="Default provider routing" onChange={(e) => setSettingValue("openrouter_provider_order", e.target.value)} />
                        </label>
                      </div>
                      <div className="openrouter-checks">
                        <label className="check-label">
                          <input type="checkbox" checked={b("openrouter_allow_fallbacks", true)} onChange={(e) => setSettingValue("openrouter_allow_fallbacks", e.target.checked)} />
                          Allow provider fallbacks
                        </label>
                        <label className="check-label">
                          <input type="checkbox" checked={b("openrouter_require_parameters", false)} onChange={(e) => setSettingValue("openrouter_require_parameters", e.target.checked)} />
                          Require requested parameters
                        </label>
                        <label className="check-label">
                          <input type="checkbox" checked={b("openrouter_include_reasoning", false)} onChange={(e) => setSettingValue("openrouter_include_reasoning", e.target.checked)} />
                          Include reasoning
                        </label>
                      </div>
                    </details>
                  </div>
                )}

                {aiRestartRequired && <div className="error-box">AI model/provider changed. Restart running services from the Services tab to make changes active.</div>}
                <button onClick={() => void saveAiSettings()} disabled={!isAdmin}>Save AI Settings</button>
              </div>
            )}

            {settingsTab === "agents" && (
              <div className="tab-content">
                <div className="panel-head">
                  <h4>Assistants/Agents</h4>
                  <div className="row">
                    <button className="ghost" onClick={() => void loadAgentsList()}>Refresh</button>
                    <button className="ghost" onClick={newAgentDraft}>Create New Assistant (Agent)</button>
                  </div>
                </div>
                <div className="split-grid">
                  <div className="list-panel">
                    {agents.map((a) => (
                      <button key={a.id} className={`list-item ${agentName === a.name ? "active" : ""}`} onClick={() => void openAgent(a.name)}>
                        <strong>{a.name}</strong>
                        <span className="muted small">v{a.version} {a.is_active ? "(active)" : "(inactive)"}</span>
                      </button>
                    ))}
                  </div>
                  <div className="detail-panel">
                    <div className="form-grid two-col">
                      <label>Name<input value={agentName} onChange={(e) => setAgentName(e.target.value)} /></label>
                      <label>Description<input value={agentDescription} onChange={(e) => setAgentDescription(e.target.value)} /></label>
                      <label className="check-label"><input type="checkbox" checked={agentActive} onChange={(e) => setAgentActive(e.target.checked)} />Active</label>
                    </div>
                    <label>Prompt<textarea className="json-editor" value={agentPrompt} onChange={(e) => setAgentPrompt(e.target.value)} /></label>
                    <div className="check-grid permission-grid">
                      {tools.map((t) => (
                        <label key={t.name} className="check-label"><input type="checkbox" checked={agentToolsSelected.includes(t.name)} onChange={() => toggleAgentTool(t.name)} />{t.name}</label>
                      ))}
                    </div>
                    <div className="row">
                      <button onClick={() => void handleSaveAgent()} disabled={!isAdmin}>Save</button>
                      <select value={agentRestoreVersion} onChange={(e) => setAgentRestoreVersion(e.target.value)}>
                        <option value="">Restore version</option>
                        {agentVersions.map((v) => <option key={v.id} value={String(v.version)}>v{v.version} - {v.created_at}</option>)}
                      </select>
                      <button className="ghost" onClick={() => void handleRestoreAgent()} disabled={!isAdmin || !agentRestoreVersion}>Restore</button>
                    </div>
                  </div>
                </div>
                {agentsMsg && <div className="info-box">{agentsMsg}</div>}
              </div>
            )}

            {settingsTab === "roles" && (
              <div className="tab-content">
                <div className="panel-head">
                  <h4>Roles</h4>
                  <div className="row">
                    <button className="ghost" onClick={() => void loadRolesList()}>Refresh</button>
                    <button className="ghost" onClick={newRoleDraft}>New</button>
                  </div>
                </div>
                <div className="split-grid">
                  <div className="list-panel">
                    {roles.map((r) => (
                      <button key={r.id} className={`list-item ${roleId === r.id ? "active" : ""}`} onClick={() => openRole(r)}>
                        <strong>{r.name}</strong>
                        <span className="muted small">{r.description || "No description"}</span>
                      </button>
                    ))}
                  </div>
                  <div className="detail-panel">
                    <div className="form-grid two-col">
                      <label>Name<input value={roleName} onChange={(e) => setRoleName(e.target.value)} /></label>
                      <label>Description<input value={roleDescription} onChange={(e) => setRoleDescription(e.target.value)} /></label>
                    </div>
                    <div className="check-grid permission-grid">
                      {agents.map((a) => (
                        <label key={a.id} className="check-label"><input type="checkbox" checked={roleAgentsSelected.includes(a.name)} onChange={() => toggleRoleAgent(a.name)} />{a.name}</label>
                      ))}
                    </div>
                    <div className="row action-row">
                      <button className={busyAction === "save-role" ? "working" : ""} onClick={() => void handleSaveRole()} disabled={!isAdmin || Boolean(busyAction)}>
                        {busyAction === "save-role" ? "Saving..." : "Save"}
                      </button>
                      <button className={`ghost ${busyAction === "delete-role" ? "working" : ""}`} onClick={() => void handleDeleteRole()} disabled={!isAdmin || roleId === null || Boolean(busyAction)}>
                        {busyAction === "delete-role" ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </div>
                </div>
                {rolesMsg && <div className="info-box">{rolesMsg}</div>}
              </div>
            )}

            {settingsTab === "users" && (
              <div className="tab-content">
                {!isAdmin && <div className="error-box">Admin access required.</div>}
                {isAdmin && (
                  <>
                    <form className="inline-form" onSubmit={handleCreateUser}>
                      <input placeholder="Username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required />
                      <input placeholder="Email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
                      <input placeholder="Mobile" value={newMobile} onChange={(e) => setNewMobile(e.target.value)} />
                      <input placeholder="WhatsApp" value={newWhatsApp} onChange={(e) => setNewWhatsApp(e.target.value)} />
                      <input placeholder="Telegram" value={newTelegram} onChange={(e) => setNewTelegram(e.target.value)} />
                      <label className="check-label"><input type="checkbox" checked={newIsAdmin} onChange={(e) => setNewIsAdmin(e.target.checked)} />Admin</label>
                      <button type="submit">Add User</button>
                    </form>
                    <div className="split-grid">
                      <div className="list-panel">
                        {users.map((u) => (
                          <button key={u.id} className={`list-item ${selectedUserId === u.id ? "active" : ""}`} onClick={() => selectUserForEdit(u)}>
                            <strong>{u.username}</strong>
                            <span className="muted small">{u.email || "(no email)"}</span>
                          </button>
                        ))}
                      </div>
                      <div className="detail-panel">
                        {selectedUserId === null ? (
                          <p className="muted">Select a user.</p>
                        ) : (
                          <>
                            <div className="form-grid user-edit-grid">
                              <label>Username<input value={userEdit.username} onChange={(e) => setUserEdit((p) => ({ ...p, username: e.target.value }))} /></label>
                              <label>Email<input value={userEdit.email} onChange={(e) => setUserEdit((p) => ({ ...p, email: e.target.value }))} /></label>
                              <label>Mobile<input value={userEdit.mobile_number} onChange={(e) => setUserEdit((p) => ({ ...p, mobile_number: e.target.value }))} /></label>
                              <label>WhatsApp<input value={userEdit.whatsapp_number} onChange={(e) => setUserEdit((p) => ({ ...p, whatsapp_number: e.target.value }))} /></label>
                              <label>Telegram<input value={userEdit.telegram_chat_id} onChange={(e) => setUserEdit((p) => ({ ...p, telegram_chat_id: e.target.value }))} /></label>
                              <label>Role
                                <select
                                  value={userEdit.role_id}
                                  onChange={(e) => {
                                    const roleId = e.target.value;
                                    setUserEdit((p) => ({
                                      ...p,
                                      role_id: roleId,
                                      role: roleNameById.get(roleId) || "",
                                    }));
                                  }}
                                >
                                  <option value="">No role</option>
                                  {userEdit.role_id && !roleNameById.has(userEdit.role_id) && (
                                    <option value={userEdit.role_id}>{userEdit.role || `Role #${userEdit.role_id}`}</option>
                                  )}
                                  {roles.map((role) => (
                                    <option key={role.id} value={String(role.id)}>{role.name}</option>
                                  ))}
                                </select>
                              </label>
                              <label>Shift
                                <select
                                  value={userEdit.shift_id ? `id:${userEdit.shift_id}` : userEdit.shift}
                                  onChange={(e) => {
                                    const value = e.target.value;
                                    if (value.startsWith("id:")) {
                                      const shiftId = value.slice(3);
                                      const found = shiftLookupOptions.find((item) => String(item.id) === shiftId);
                                      setUserEdit((p) => ({ ...p, shift_id: shiftId, shift: found?.name || "" }));
                                    } else {
                                      setUserEdit((p) => ({ ...p, shift_id: "", shift: value }));
                                    }
                                  }}
                                >
                                  <option value="">No shift</option>
                                  {shiftLookupOptions.map((shift) => <option key={`shift-${shift.id}`} value={`id:${shift.id}`}>{shift.name}</option>)}
                                  {shiftOptions
                                    .filter((shift) => !shiftLookupOptions.some((item) => item.name.toLowerCase() === shift.toLowerCase()))
                                    .map((shift) => <option key={shift} value={shift}>{shift}</option>)}
                                </select>
                              </label>
                              <label>Department
                                <select
                                  value={userEdit.department_id ? `id:${userEdit.department_id}` : userEdit.department}
                                  onChange={(e) => {
                                    const value = e.target.value;
                                    if (value.startsWith("id:")) {
                                      const departmentId = value.slice(3);
                                      const found = departmentLookupOptions.find((item) => String(item.id) === departmentId);
                                      setUserEdit((p) => ({ ...p, department_id: departmentId, department: found?.name || "" }));
                                    } else {
                                      setUserEdit((p) => ({ ...p, department_id: "", department: value }));
                                    }
                                  }}
                                >
                                  <option value="">No department</option>
                                  {departmentLookupOptions.map((department) => <option key={`department-${department.id}`} value={`id:${department.id}`}>{department.name}</option>)}
                                  {departmentOptions
                                    .filter((department) => !departmentLookupOptions.some((item) => item.name.toLowerCase() === department.toLowerCase()))
                                    .map((department) => <option key={department} value={department}>{department}</option>)}
                                </select>
                              </label>
                              <label className="check-label"><input type="checkbox" checked={userEdit.is_active} onChange={(e) => setUserEdit((p) => ({ ...p, is_active: e.target.checked }))} />Active</label>
                              <label className="check-label"><input type="checkbox" checked={userEdit.is_admin} onChange={(e) => setUserEdit((p) => ({ ...p, is_admin: e.target.checked }))} />Admin</label>
                            </div>
                            <div className="row action-row">
                              <button type="button" className={busyAction === "save-user" ? "working" : ""} onClick={() => void handleSaveUserEdit()} disabled={Boolean(busyAction)}>
                                {busyAction === "save-user" ? "Saving..." : "Save User"}
                              </button>
                              <button type="button" className={`ghost ${busyAction === "set-active-user" ? "working" : ""}`} onClick={() => void handleSetActiveUserContext()} disabled={Boolean(busyAction)}>
                                {busyAction === "set-active-user" ? "Setting..." : "Set Active User"}
                              </button>
                              <button type="button" className={`ghost ${busyAction === "send-password" ? "working" : ""}`} onClick={() => void handleSendNewPassword(selectedUserId)} disabled={Boolean(busyAction)}>
                                {busyAction === "send-password" ? "Sending..." : "Send New Password"}
                              </button>
                              {manualPasswordNotice && (
                                <button type="button" className="ghost" onClick={() => setManualPasswordNotice("")}>Clear Password</button>
                              )}
                            </div>
                            {manualPasswordNotice && <div className="info-box">{manualPasswordNotice}</div>}
                            {lastTempPassword && (
                              <div className="info-box">
                                <div className="row">
                                  <strong>Temporary Password for {lastTempPasswordUser || "selected user"}:</strong>
                                  <button type="button" className="ghost" onClick={() => void copyTemporaryPassword()}>Copy Password</button>
                                </div>
                                <input readOnly value={lastTempPassword} />
                              </div>
                            )}
                            {usersMsg && <div className="info-box">{usersMsg}</div>}
                          </>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {settingsTab === "tools" && (
              <div className="tab-content">
                <div className="panel-head">
                  <h4>System Tools</h4>
                  <div className="row">
                    <button className="ghost" onClick={() => void loadToolsList()}>Reload</button>
                    <button onClick={() => void handleRefreshToolRegistry()} disabled={!isAdmin}>Refresh Registry</button>
                  </div>
                </div>
                <div className="split-grid">
                  <div className="list-panel">
                    {tools.map((t) => (
                      <button key={t.name} className={`list-item ${selectedToolName === t.name ? "active" : ""}`} onClick={() => selectTool(t.name)}>
                        <strong>{t.name}</strong>
                        <span className="muted small">{t.version || "-"}</span>
                      </button>
                    ))}
                  </div>
                  <div className="detail-panel">
                    {selectedTool ? (
                      <>
                        <h5>{selectedTool.name}</h5>
                        <label>Description<textarea className="json-editor short" value={toolDescriptionDraft} onChange={(e) => setToolDescriptionDraft(e.target.value)} /></label>
                        <label>Input Schema<textarea className="json-editor short" value={selectedTool.input_schema || ""} readOnly /></label>
                        <label>Output Schema<textarea className="json-editor short" value={selectedTool.output_schema || ""} readOnly /></label>
                        <label>Example Call<textarea className="json-editor short" value={selectedTool.example_call || ""} readOnly /></label>
                        <button onClick={() => void handleSaveToolDescription()} disabled={!isAdmin}>Save Description</button>
                      </>
                    ) : (
                      <p className="muted">Select a tool.</p>
                    )}
                  </div>
                </div>
                {toolsMsg && <div className="info-box">{toolsMsg}</div>}
              </div>
            )}

            {settingsTab === "email" && (
              <div className="tab-content">
                <div className="form-grid two-col">
                  <label className="check-label"><input type="checkbox" checked={b("gmail_enabled", false)} onChange={(e) => setSettingValue("gmail_enabled", e.target.checked)} />Enable Gmail email sending</label>
                  <label>Sender Gmail Address<input value={s("gmail_sender_email", "")} onChange={(e) => setSettingValue("gmail_sender_email", e.target.value)} /></label>
                  <label>Sender Display Name<input value={s("gmail_sender_name", "")} onChange={(e) => setSettingValue("gmail_sender_name", e.target.value)} /></label>
                  <label>Gmail App Password<input type="password" value={s("gmail_app_password", "")} onChange={(e) => setSettingValue("gmail_app_password", e.target.value)} /></label>
                  <label>Test Recipient<input value={s("gmail_test_to", "")} onChange={(e) => setSettingValue("gmail_test_to", e.target.value)} /></label>
                  <label>Test Subject<input value={s("gmail_test_subject", "Test Email from OASIS")} onChange={(e) => setSettingValue("gmail_test_subject", e.target.value)} /></label>
                  <label>Test Body<input value={s("gmail_test_body", "Hello from OASIS")} onChange={(e) => setSettingValue("gmail_test_body", e.target.value)} /></label>
                </div>
                <div className="muted small">The `send_gmail_email` tool reads the sender Gmail address and app password from these saved settings.</div>
                <div className="row">
                  <button onClick={() => void saveEmailSettings()} disabled={!isAdmin}>Save</button>
                  <button className="ghost" onClick={() => void doEmailTest()} disabled={!isAdmin}>Send</button>
                </div>
              </div>
            )}

            {settingsTab === "telegram" && (
              <div className="tab-content">
                <div className="whatsapp-status-card">
                  <div className="whatsapp-status-head">Telegram Service</div>
                  <div className="whatsapp-chip-row">
                    <span className={`status ${telegramEnabled ? "ok" : "bad"}`}>{telegramEnabled ? "Enabled" : "Disabled"}</span>
                    <span className={`status ${telegramHasToken ? "ok" : "bad"}`}>{telegramHasToken ? "Token Present" : "Token Missing"}</span>
                    <span className={`status ${telegramRunning ? "ok" : "bad"}`}>{telegramRunning ? "Running" : "Stopped"}</span>
                  </div>
                  <div className="whatsapp-status-list">
                    <div><strong>Stage:</strong> {titleCaseStatus(telegramStage) || "Unknown"}</div>
                    <div><strong>Message:</strong> {telegramStatusMessage || "No status message yet."}</div>
                    <div><strong>Poll Timeout:</strong> {asString(telegramState.poll_timeout, "") || "-"} s</div>
                    <div><strong>Retry Delay:</strong> {asString(telegramState.poll_retry_seconds, "") || "-"} s</div>
                    <div><strong>Last Error:</strong> {telegramLastError || "None"}</div>
                  </div>
                </div>
                <div className="form-grid two-col">
                  <label className="check-label"><input type="checkbox" checked={b("telegram_enabled", false)} onChange={(e) => setSettingValue("telegram_enabled", e.target.checked)} />Enable Telegram</label>
                  <label>Bot Token<input type="password" value={s("telegram_bot_token", "")} onChange={(e) => setSettingValue("telegram_bot_token", e.target.value)} /></label>
                  <label>Poll Timeout<input type="number" value={n("telegram_poll_timeout", 25)} onChange={(e) => setSettingValue("telegram_poll_timeout", asNumber(e.target.value, 25))} /></label>
                  <label>Retry Delay<input type="number" step={0.1} value={n("telegram_poll_retry_seconds", 2)} onChange={(e) => setSettingValue("telegram_poll_retry_seconds", asNumber(e.target.value, 2))} /></label>
                  <label>Test Chat ID<input value={s("telegram_test_chat_id", "")} onChange={(e) => setSettingValue("telegram_test_chat_id", e.target.value)} /></label>
                  <label>Test Message<input value={s("telegram_test_message", "Hello from Desktop Agentic System")} onChange={(e) => setSettingValue("telegram_test_message", e.target.value)} /></label>
                </div>
                <div className="row">
                  <button onClick={() => void saveTelegramSettings()} disabled={!isAdmin}>Save</button>
                  <button className="ghost" onClick={() => void doTelegramRestart()} disabled={!isAdmin}>Restart</button>
                  <button className="ghost" onClick={() => void doTelegramStop()} disabled={!isAdmin}>Stop</button>
                  <button className="ghost" onClick={() => void doTelegramTest()} disabled={!isAdmin}>Send Test</button>
                </div>
                <details className="whatsapp-details">
                  <summary>Raw Telegram Status</summary>
                  <pre className="whatsapp-raw">{pretty(integrations?.telegram || {})}</pre>
                </details>
              </div>
            )}

            {settingsTab === "whatsapp" && (
              <div className="tab-content">
                {!isAdmin && <div className="error-box">Admin access required for registration, linking, and daemon controls.</div>}

                {isAdmin && (
                  <div className="whatsapp-shell">
                    <div className="whatsapp-status-grid">
                      <div className="whatsapp-status-card">
                        <div className="whatsapp-status-head">Headless Bridge</div>
                        <div className="whatsapp-chip-row">
                          <span className={`status ${whatsappHeadlessReady ? "ok" : "bad"}`}>{whatsappHeadlessReady ? "Ready" : "Needs Setup"}</span>
                          <span className={`status ${whatsappRegisterRunning ? "ok" : "bad"}`}>Register {whatsappRegisterRunning ? "Running" : "Idle"}</span>
                          <span className={`status ${whatsappDaemonRunning ? "ok" : "bad"}`}>Daemon {whatsappDaemonRunning ? "Running" : "Stopped"}</span>
                        </div>
                        <div className="whatsapp-status-list">
                          <div><strong>Runtime:</strong> {whatsappPackagedBridge ? "Packaged Windows bridge" : whatsappNodeAvailable ? "Node.js bridge" : "Missing"}</div>
                          <div><strong>Node:</strong> {whatsappNodeAvailable ? "Available" : "Missing"} {asString(whatsappNode.path, "")}</div>
                          <div><strong>register.js:</strong> {whatsappRegisterExists ? "Found" : "Missing"}</div>
                          <div><strong>daemon.js:</strong> {whatsappDaemonExists ? "Found" : "Missing"}</div>
                          <div><strong>register.exe:</strong> {whatsappRegisterExeExists ? "Found" : "Missing"}</div>
                          <div><strong>daemon.exe:</strong> {whatsappDaemonExeExists ? "Found" : "Missing"}</div>
                          <div><strong>Auth Session:</strong> {whatsappAuthLinked ? "Linked" : "Not linked"}</div>
                          <div><strong>Register Stage:</strong> {titleCaseStatus(asString(whatsappRegisterState.stage, "idle")) || "Idle"}</div>
                          <div><strong>Register Error:</strong> {whatsappRegisterError || "None"}</div>
                          <div><strong>Daemon Stage:</strong> {titleCaseStatus(asString(whatsappDaemonState.stage, "stopped")) || "Stopped"}</div>
                          <div><strong>Daemon Error:</strong> {whatsappDaemonError || "None"}</div>
                        </div>
                      </div>

                      <div className="whatsapp-status-card">
                        <div className="whatsapp-status-head">Folder & Runtime</div>
                        <div className="whatsapp-status-list">
                          <div><strong>Storage Root:</strong> {storageRoot}</div>
                          <div><strong>Bridge Folder (Configured):</strong> {configuredBridgeFolder || "Not set"}</div>
                          <div><strong>Bridge Folder (Saved in Bridge):</strong> {fileBridgeFolder || "Not set"}</div>
                          <div><strong>Bridge Folder (Active):</strong> {activeBridgeFolder || "Not resolved"}</div>
                          <div><strong>Legacy Service:</strong> {whatsappLegacyRunning ? "Running" : "Stopped"}</div>
                        </div>
                      </div>
                    </div>

                    {!whatsappHeadlessReady && (
                      <div className="error-box">
                        Headless prerequisites are missing. Use the packaged bridge files or ensure Node.js is in PATH for the API process, then restart the API service.
                      </div>
                    )}

                    <section className="whatsapp-section card">
                      <div className="whatsapp-section-title">Whatsap Phone Linking</div>
                      <div className="whatsapp-link-row">
                        <label>Whatsap Number
                          <input placeholder="919876543210" value={whatsappRegisterPhone} onChange={(e) => setWhatsAppRegisterPhone(e.target.value)} />
                        </label>
                        <button
                          className={whatsappHeadlessBusy === "register_start" ? "working" : ""}
                          onClick={() => void startWhatsAppRegistrationFlow()}
                          disabled={Boolean(whatsappHeadlessBusy) || !whatsappRegisterPhone.trim()}
                        >
                          {whatsappHeadlessBusy === "register_start" ? "Registering..." : "Register"}
                        </button>
                        <button
                          className="ghost"
                          onClick={() => void stopWhatsAppRegistrationFlow()}
                          disabled={Boolean(whatsappHeadlessBusy) || !whatsappRegistrationStoppable}
                        >
                          {whatsappHeadlessBusy === "register_stop" ? "Stopping..." : "Stop Registration"}
                        </button>
                        <div className="whatsapp-code-inline">{whatsappPairingCode || "---- ----"}</div>
                        <button className="ghost" onClick={() => void logoutWhatsAppLinkFlow()} disabled={Boolean(whatsappHeadlessBusy)}>Log Out</button>
                      </div>
                      <div className="muted small">After Register, enter the shown code in WhatsApp &gt; Linked Devices &gt; Link with phone number.</div>
                    </section>

                    <section className="whatsapp-section card">
                      <div className="whatsapp-section-title">Additional Settings</div>
                      <div className="form-grid two-col">
                        <label className="check-label"><input type="checkbox" checked={b("whatsapp_enabled", false)} onChange={(e) => setSettingValue("whatsapp_enabled", e.target.checked)} />Enable WhatsApp</label>
                        <label>Poll Seconds<input type="number" step={0.1} value={n("whatsapp_poll_seconds", 1)} onChange={(e) => setSettingValue("whatsapp_poll_seconds", asNumber(e.target.value, 1))} /></label>
                        <label>Test To<input value={s("whatsapp_test_to", "")} onChange={(e) => setSettingValue("whatsapp_test_to", e.target.value)} /></label>
                        <label>Test Message<input value={s("whatsapp_test_message", "Hello from Desktop Agentic System")} onChange={(e) => setSettingValue("whatsapp_test_message", e.target.value)} /></label>
                      </div>
                      <div className="row">
                        <button onClick={() => void saveWhatsAppSettings()} disabled={!isAdmin}>Save Additional Settings</button>
                        <button className="ghost" onClick={() => void loadWhatsAppHeadlessStatus()} disabled={Boolean(whatsappHeadlessBusy)}>Refresh Status</button>
                        <button onClick={() => void startWhatsAppDaemonFlow()} disabled={Boolean(whatsappHeadlessBusy) || whatsappDaemonRunning}>Start Daemon</button>
                        <button className="ghost" onClick={() => void stopWhatsAppDaemonFlow()} disabled={Boolean(whatsappHeadlessBusy) || !whatsappDaemonRunning}>Stop Daemon</button>
                        <button className="ghost" onClick={() => void doWhatsAppTest()} disabled={!isAdmin}>Send Test</button>
                      </div>
                    </section>

                    <details className="whatsapp-details">
                      <summary>Bridge Logs</summary>
                      <label>Register Logs<textarea className="json-editor short" readOnly value={whatsappRegisterLogs || "No register logs yet."} /></label>
                      <label>Daemon Logs<textarea className="json-editor short" readOnly value={whatsappDaemonLogs || "No daemon logs yet."} /></label>
                    </details>

                    <details className="whatsapp-details">
                      <summary>Legacy Service Raw Status</summary>
                      <pre className="whatsapp-raw">{pretty(integrations?.whatsapp || {})}</pre>
                    </details>

                    {whatsappHeadlessMsg && <div className="info-box">{whatsappHeadlessMsg}</div>}
                  </div>
                )}
              </div>
            )}

                        {settingsTab === "services" && (
              <div className="tab-content">
                {!isAdmin && <div className="error-box">Admin access required to control services.</div>}
                {isAdmin && (
                  <>
                    {aiRestartRequired && <div className="error-box">Model changes are pending. Use Restart to apply API/UI changes.</div>}
                    <div className="services-grid">
                      <div className="service-card card">
                        <h5>API Service</h5>
                        <p className="muted small">Status: {serviceRunning("api") ? "Running" : "Stopped"}</p>
                        <div className="row">
                          <button className="ghost" onClick={() => void handleApiService("stop")} disabled={!isAdmin}>Stop</button>
                          <button className="ghost" onClick={() => void handleApiService("restart")} disabled={!isAdmin || !serviceRunning("api")}>Restart</button>
                        </div>
                      </div>
                      <div className="service-card card">
                        <h5>Web UI Service</h5>
                        <p className="muted small">Status: {serviceRunning("web_ui") ? "Running" : "Stopped"}</p>
                        <div className="row">
                          <button className="ghost" onClick={() => void handleWebUiService("stop")} disabled={!isAdmin}>Stop</button>
                          <button className="ghost" onClick={() => void handleWebUiService("restart")} disabled={!isAdmin || !serviceRunning("web_ui")}>Restart</button>
                        </div>
                      </div>
                    </div>
                    <div className="info-box">Telegram and WhatsApp are managed in their own tabs. This tab only controls API and Web UI.</div>
                  </>
                )}
              </div>
            )}

                        {settingsTab === "scheduler" && (
              <div className="tab-content scheduler-shell">
                <section className="card scheduler-section">
                  <h5>Scheduler Service</h5>
                  <div className="scheduler-service-head">
                    <p>Status: {asBool(schedulerStatus.running, false) ? "running" : "stopped"} (poll={asNumber(schedulerStatus.poll_minutes, n("scheduler_poll_minutes", 1))}m)</p>
                    <div className="row">
                      <button className="ghost" onClick={() => void loadSchedulerStatus()}>Refresh Status</button>
                      <button className="ghost" onClick={() => void handleRestartScheduler()} disabled={!isAdmin}>Restart Scheduler</button>
                    </div>
                  </div>
                </section>

                <section className="card scheduler-section">
                  <h5>Execution Settings</h5>
                  <div className="scheduler-exec-grid">
                    <label className="check-label"><input type="checkbox" checked={b("scheduler_enabled", false)} onChange={(e) => setSettingValue("scheduler_enabled", e.target.checked)} />Enable scheduler service</label>
                    <label>Poll frequency (minutes)
                      <input type="number" min={1} max={1440} value={n("scheduler_poll_minutes", 1)} onChange={(e) => setSettingValue("scheduler_poll_minutes", asNumber(e.target.value, 1))} />
                    </label>
                  </div>
                </section>

                <section className="card scheduler-section">
                  <div className="subtab-row scheduler-subtabs">
                    <button className={schedulerView === "list" ? "active" : ""} onClick={() => setSchedulerView("list")}>Schedule List</button>
                    <button className={schedulerView === "create" ? "active" : ""} onClick={newScheduleDraft}>Create Schedule</button>
                    <button className={schedulerView === "editor" ? "active" : ""} onClick={() => setSchedulerView("editor")}>Schedule Editor</button>
                  </div>

                  {schedulerView === "list" && (
                    <>
                      <h5>Schedules</h5>
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Next Run</th><th>Enabled</th><th>Task Prompt</th></tr></thead>
                          <tbody>
                            {schedulerItems.map((item) => {
                              const raw = item as unknown as Record<string, unknown>;
                              const id = asNumber(raw.id, 0);
                              return (
                                <tr key={id} onClick={() => openSchedule(item)} className="scheduler-row">
                                  <td>{id}</td><td>{asString(raw.title)}</td><td>{asString(raw.schedule_type)}</td><td>{asString(raw.next_run_at)}</td><td>{asBool(raw.is_enabled, false) ? "Yes" : "No"}</td><td>{asString(raw.task_prompt)}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                        {schedulerItems.length === 0 && <p className="muted table-empty">No schedules.</p>}
                      </div>
                      <div className="row">
                        <button className="ghost" onClick={() => void loadSchedulesList()}>Refresh List</button>
                        <button className="ghost" onClick={newScheduleDraft} disabled={!isAdmin}>New Schedule</button>
                        <button className="ghost" onClick={() => scheduleForm.id && void handleDeleteSchedule(scheduleForm.id)} disabled={!isAdmin || !scheduleForm.id}>Delete</button>
                      </div>
                    </>
                  )}

                  {schedulerView === "create" && (
                    <>
                      <h5>Create From Natural Language</h5>
                      <p className="muted">Describe the schedule in plain language. Validate fills the editor; Validate + Create saves it immediately.</p>
                      <label>
                        <textarea className="json-editor" placeholder="Example: every weekday at 9am send daily sales summary to management" value={scheduleNlRequest} onChange={(e) => setScheduleNlRequest(e.target.value)} />
                      </label>
                      <div className="row">
                        <button className="ghost" onClick={() => setSchedulerView("list")}>Back To List</button>
                        <div className="spacer" />
                        <button className="ghost" onClick={() => void handleValidateSchedule()}>Validate</button>
                        <button
                          onClick={async () => {
                            await handleValidateSchedule();
                            await handleSaveSchedule();
                          }}
                          disabled={!isAdmin}
                        >
                          Validate + Create
                        </button>
                      </div>
                    </>
                  )}

                  {schedulerView === "editor" && (
                    <>
                      <h5>Schedule Editor</h5>
                      <div className="form-grid two-col">
                        <label>ID<input value={scheduleForm.id ? String(scheduleForm.id) : "New"} readOnly /></label>
                        <label>Title<input value={scheduleForm.title} onChange={(e) => setScheduleForm((p) => ({ ...p, title: e.target.value }))} /></label>
                        <label>Type<input value={scheduleForm.schedule_type} onChange={(e) => setScheduleForm((p) => ({ ...p, schedule_type: e.target.value }))} /></label>
                        <label>Timezone<input value={scheduleForm.timezone} onChange={(e) => setScheduleForm((p) => ({ ...p, timezone: e.target.value }))} /></label>
                        <label>Interval<input type="number" min={0} value={scheduleForm.interval_minutes} onChange={(e) => setScheduleForm((p) => ({ ...p, interval_minutes: asNumber(e.target.value, 0) }))} /></label>
                        <label>Hour<input type="number" min={0} max={23} value={scheduleForm.run_hour} onChange={(e) => setScheduleForm((p) => ({ ...p, run_hour: asNumber(e.target.value, 9) }))} /></label>
                        <label>Minute<input type="number" min={0} max={59} value={scheduleForm.run_minute} onChange={(e) => setScheduleForm((p) => ({ ...p, run_minute: asNumber(e.target.value, 0) }))} /></label>
                        <label>Weekday<input type="number" min={0} max={6} value={scheduleForm.run_day_of_week} onChange={(e) => setScheduleForm((p) => ({ ...p, run_day_of_week: asNumber(e.target.value, 0) }))} /></label>
                        <label>Day Of Month<input type="number" min={1} max={31} value={scheduleForm.run_day_of_month} onChange={(e) => setScheduleForm((p) => ({ ...p, run_day_of_month: asNumber(e.target.value, 1) }))} /></label>
                        <label className="check-label"><input type="checkbox" checked={scheduleForm.is_enabled} onChange={(e) => setScheduleForm((p) => ({ ...p, is_enabled: e.target.checked }))} />Enabled</label>
                      </div>
                      <label>Task Prompt<textarea className="json-editor short" value={scheduleForm.task_prompt} onChange={(e) => setScheduleForm((p) => ({ ...p, task_prompt: e.target.value }))} /></label>
                      <div className="row">
                        <button onClick={() => void handleSaveSchedule()} disabled={!isAdmin}>Save Schedule</button>
                        <button className="ghost" onClick={() => scheduleForm.id && void handleRunSchedule(scheduleForm.id)} disabled={!isAdmin || !scheduleForm.id}>Run</button>
                        <button className="ghost" onClick={() => scheduleForm.id && void handleDeleteSchedule(scheduleForm.id)} disabled={!isAdmin || !scheduleForm.id}>Delete</button>
                      </div>
                      <label>Last Result<textarea className="json-editor short" value={scheduleForm.last_result} readOnly /></label>
                    </>
                  )}
                </section>

                <div className="row scheduler-footer-actions">
                  <button className="ghost" onClick={() => void handleStopScheduler()} disabled={!isAdmin}>Stop Scheduler</button>
                  <button onClick={() => void saveSchedulerSettings()} disabled={!isAdmin}>Save Apply Changes</button>
                </div>
              </div>
            )}

            {settingsMsg && <div className="info-box">{settingsMsg}</div>}
            {integrationsMsg && <div className="info-box">{integrationsMsg}</div>}
            {schedulerMsg && <div className="info-box">{schedulerMsg}</div>}
          </section>
        )}

        {mainTab === "profile" && (
          <section className="panel card">
            <h3>Profile</h3>
            <p><strong>Username:</strong> {user.username}</p>
            <p><strong>Email:</strong> {user.email || "(none)"}</p>
            <p><strong>Admin:</strong> {user.is_admin ? "Yes" : "No"}</p>
            <p><strong>API:</strong> {apiBase}</p>
            <p><strong>Current User Context ID:</strong> {s("current_user_id", "") || "(not set)"}</p>
            <p><strong>Current User Context Email:</strong> {s("current_user_email", "") || "(not set)"}</p>
          </section>
        )}
      </main>
    </div>
  );
}















































































































