export interface PiiEntity {
  label: string;
  score: number;
  text: string;
  start?: number;
  end?: number;
  method?: string;
  context_boost?: boolean;
  corroborated?: boolean;
}

export interface Diagnostic {
  gate: string;
  ran: boolean;
  skipped_reason?: string | null;
  duration_ms?: number;
  blocked?: boolean;
  note?: string | null;
}

export interface ScreenResult {
  classify: {
    safe: boolean;
    category: string | null;
    categories: string[];
    confidence: number;
    description: string | null;
  };
  pii: { has_pii: boolean; entities: PiiEntity[]; masked_text: string | null };
  text: string;
  _diagnostics: Diagnostic[];
  scope?: { allowed: boolean; matched_topic: string | null };
}

export type ConfigFieldType =
  | "enum"
  | "enum_or_null"
  | "float"
  | "float_or_null"
  | "string_list"
  | "string_map"
  | "string_list_map"
  | "route_list";

export type GateName =
  | "injection"
  | "safety"
  | "pii"
  | "scope"
  | "routes"
  | "grounding";

export type GateStatus =
  | "flagged"
  | "clean"
  | "degraded"
  | "skipped"
  | "unavailable";

export interface GateDetail {
  label: string;
  severity: string;
  text: string;
  method?: string;
}

export interface GateResult {
  name: GateName;
  status: GateStatus;
  summary: string;
  duration_ms: number;
  detail: GateDetail[];
  note: string;
}

export interface PlaygroundResult {
  gates: GateResult[];
  text: string;
  total_ms: number;
  request_id: string | null;
  decided_by: string;
  degraded: boolean;
}

export interface Sample {
  gate: GateName;
  label: string;
  text: string;
  sources: string[] | null;
  config: Record<string, unknown>;
}

export interface ConfigField {
  name: string;
  type: ConfigFieldType;
  default: unknown;
  label: string;
  group: string;
  help: string;
  choices: string[] | null;
  min: number | null;
  max: number | null;
  step: number | null;
  options_source: string | null;
}

export interface ConfigSchema {
  fields: ConfigField[];
  gate_groups: Record<GateName, string[]>;
  options: {
    pii_entities: string[];
    categories: Array<{ value: string; label: string }>;
  };
}

export type ConfigMap = Record<string, unknown>;

export interface ScreenEvent {
  ts: number;
  stage: string;
  action: "pass" | "mask" | "block" | "flag";
  safe: boolean;
  category: string | null;
  confidence: number;
  pii_count: number;
  pii_labels: string[];
  latency_ms: number;
  gates: Record<string, number>;
  flagged: string[];
  decided_by: string;
  degraded: boolean;
  request_id: string | null;
  text: string | null;
}

export interface LogStats {
  total: number;
  passed: number;
  blocked: number;
  masked: number;
  flagged: number;
  caught: number;
  pii_total: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  categories: Record<string, number>;
  series: Array<{ t: number; v: number }>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      body?.detail ?? body?.error?.message ?? `Request failed: ${res.status}`,
    );
  }
  return res.json() as Promise<T>;
}

export const screen = (body: Record<string, unknown>) =>
  req<ScreenResult>("/v1/screen", { method: "POST", body: JSON.stringify(body) });

export const runPlayground = (body: {
  text: string;
  stage?: string;
  sources?: string[];
  overrides?: Record<string, unknown>;
}) =>
  req<PlaygroundResult>("/v1/playground", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getSamples = () => req<{ samples: Sample[] }>("/v1/samples");

export const getConfig = () => req<{ config: ConfigMap }>("/v1/config");
export const getConfigSchema = () => req<ConfigSchema>("/v1/config/schema");
export const putConfig = (patch: ConfigMap) =>
  req<{ config: ConfigMap }>("/v1/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
export const resetConfig = () =>
  req<{ config: ConfigMap }>("/v1/config/reset", { method: "POST" });
export const saveConfig = () =>
  req<{ path: string }>("/v1/config/save", { method: "POST" });

export const getLogs = (limit = 200) =>
  req<{ events: ScreenEvent[]; store_text: boolean }>(`/v1/logs?limit=${limit}`);
export const getLogStats = () => req<LogStats>("/v1/logs/stats");
export const clearLogs = () => req<{ cleared: boolean }>("/v1/logs", { method: "DELETE" });

export const getMeta = () =>
  req<{ version: string; ui: boolean; engines: Record<string, boolean> }>("/v1/meta");
