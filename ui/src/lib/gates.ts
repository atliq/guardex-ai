import type { GateName } from "@/lib/api";

export const GATE_LABELS: Record<string, string> = {
  injection: "Prompt injection",
  safety: "Content safety",
  pii: "Personal data",
  scope: "Topic scope",
  routes: "Custom routes",
  grounding: "Grounding",
};

export const GATE_SHORT: Record<string, string> = {
  injection: "injection",
  safety: "safety",
  pii: "PII",
  scope: "scope",
  routes: "routes",
  grounding: "grounding",
};

export const GATE_BLURB: Record<string, string> = {
  injection: "Jailbreaks and instruction overrides, matched by regex",
  safety: "Toxicity and the S1-S14 harm categories",
  pii: "31 entity types plus your own regex patterns",
  scope: "Keeps the conversation on topics you allow",
  routes: "Your own blocklist, defined by example utterances",
  grounding: "Checks claims against reference sources you provide",
};

export function gateLabel(name: string): string {
  return GATE_LABELS[name] ?? name;
}

/** "Content safety" / "Content safety and Personal data" / "3 gates" */
export function namedGates(names: GateName[]): string {
  const labels = names.map(gateLabel);
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} and ${labels[1]}`;
  return `${labels.length} gates`;
}
