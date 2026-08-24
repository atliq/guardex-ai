import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  Check,
  ChevronDown,
  Clock,
  Crosshair,
  EyeOff,
  FileText,
  GitBranch,
  Info,
  RotateCcw,
  Save,
  Scale,
  ScanEye,
  Settings2,
  Shield,
  ShieldCheck,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";
import { ConfigFieldControl } from "@/components/ConfigFieldControl";
import {
  getConfig,
  getConfigSchema,
  putConfig,
  saveConfig,
  type ConfigField,
  type ConfigMap,
  type ConfigSchema,
} from "@/lib/api";

const SECTION_META: Record<
  string,
  { label: string; title: string; description: string; icon: LucideIcon }
> = {
  pii: {
    label: "PII",
    title: "PII",
    icon: Shield,
    description:
      "Control how GuardEx detects and handles personally identifiable information.",
  },
  content: {
    label: "Content",
    title: "Content safety",
    icon: FileText,
    description:
      "Choose which categories are blocked and how the classifier cascade runs.",
  },
  scope: {
    label: "Topic scope",
    title: "Topic scope",
    icon: Crosshair,
    description: "Keep requests on the topics you allow.",
  },
  routes: {
    label: "Custom routes",
    title: "Custom routes",
    icon: GitBranch,
    description: "Block your own categories using example utterances.",
  },
  grounding: {
    label: "Grounding",
    title: "Grounding",
    icon: Scale,
    description:
      "Control how GuardEx verifies whether responses are supported by the available context.",
  },
};

const NAV_GROUPS: Array<{ label: string; keys: string[] }> = [
  { label: "Protection", keys: ["pii", "content", "scope"] },
  { label: "Routing", keys: ["routes", "grounding"] },
];

const same = (a: unknown, b: unknown) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/* ---------- shared building blocks ---------- */

function RadioDot({ selected }: { selected: boolean }) {
  return (
    <span
      className={cn(
        "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
        selected ? "border-primary" : "border-muted-foreground/40",
      )}
    >
      {selected && <span className="h-2 w-2 rounded-full bg-primary" />}
    </span>
  );
}

function Chip({
  tone,
  children,
}: {
  tone: "green" | "violet" | "muted";
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        tone === "green" && "bg-success/10 text-success",
        tone === "violet" && "bg-primary/10 text-primary",
        tone === "muted" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

interface Choice {
  value: string | null;
  title: string;
  description: string;
  icon: LucideIcon;
  badge?: { text: string; tone: "green" | "violet" };
  meta?: string;
}

function ChoiceCards({
  choices,
  value,
  onChange,
  columns = 3,
}: {
  choices: Choice[];
  value: unknown;
  onChange: (v: string | null) => void;
  columns?: 2 | 3 | 4;
}) {
  const current = value ?? null;
  return (
    <div
      role="radiogroup"
      className={cn(
        "grid grid-cols-1 gap-3",
        columns === 2 && "md:grid-cols-2",
        columns === 3 && "md:grid-cols-3",
        columns === 4 && "md:grid-cols-2 xl:grid-cols-4",
      )}
    >
      {choices.map((c) => {
        const selected = current === c.value;
        return (
          <button
            key={String(c.value)}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(c.value)}
            className={cn(
              "flex flex-col items-start gap-2 rounded-lg border p-4 text-left transition-colors",
              selected
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border bg-card hover:border-primary/40",
            )}
          >
            <div className="flex w-full items-center gap-2">
              <RadioDot selected={selected} />
              <c.icon
                className={cn(
                  "h-4 w-4",
                  selected ? "text-primary" : "text-muted-foreground",
                )}
              />
              <span className="text-sm font-semibold">{c.title}</span>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {c.description}
            </p>
            {c.badge && <Chip tone={c.badge.tone}>{c.badge.text}</Chip>}
            {c.meta && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Clock className="h-3 w-3" />
                {c.meta}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function SettingCard({
  title,
  description,
  badge,
  children,
}: {
  title: string;
  description?: string;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            {description && (
              <p className="mt-1 text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          {badge}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-primary/15 bg-primary/5 px-3 py-2 text-xs text-foreground/80">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
      <span>{children}</span>
    </div>
  );
}

function ThresholdSlider({
  field,
  value,
  onChange,
}: {
  field: ConfigField;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {field.min} – {field.max}
        </span>
        <span className="font-mono tabular-nums text-foreground">
          {value.toFixed(2)}
        </span>
      </div>
      <Slider
        value={[value]}
        min={field.min ?? 0}
        max={field.max ?? 1}
        step={field.step ?? 0.05}
        onValueChange={([v]) => onChange(v)}
      />
    </div>
  );
}

function AutoOrCustomCard({
  title,
  description,
  autoTitle,
  autoDescription,
  customDescription,
  field,
  value,
  onChange,
}: {
  title: string;
  description: string;
  autoTitle: string;
  autoDescription: string;
  customDescription: string;
  field: ConfigField;
  value: unknown;
  onChange: (v: number | null) => void;
}) {
  const isAuto = value === null || value === undefined;
  return (
    <SettingCard title={title} description={description}>
      <div className="divide-y divide-border rounded-lg border border-border">
        <button
          type="button"
          role="radio"
          aria-checked={isAuto}
          onClick={() => onChange(null)}
          className="flex w-full items-center gap-3 p-4 text-left"
        >
          <RadioDot selected={isAuto} />
          <div className="flex-1">
            <span className="text-sm font-medium">
              {autoTitle}{" "}
              <span className="text-muted-foreground">(recommended)</span>
            </span>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {autoDescription}
            </p>
          </div>
          {isAuto && (
            <Chip tone="green">
              <Check className="h-3 w-3" />
              Active
            </Chip>
          )}
        </button>
        <div>
          <button
            type="button"
            role="radio"
            aria-checked={!isAuto}
            onClick={() => {
              if (isAuto) onChange((field.max ?? 1) / 2);
            }}
            className="flex w-full items-center gap-3 p-4 text-left"
          >
            <RadioDot selected={!isAuto} />
            <div className="flex-1">
              <span className="text-sm font-medium">Custom</span>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {customDescription}
              </p>
            </div>
            {!isAuto && (
              <Chip tone="green">
                <Check className="h-3 w-3" />
                Active
              </Chip>
            )}
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                !isAuto && "rotate-180",
              )}
            />
          </button>
          {!isAuto && (
            <div className="px-4 pb-4 pl-11">
              <ThresholdSlider
                field={field}
                value={Number(value)}
                onChange={onChange}
              />
            </div>
          )}
        </div>
      </div>
    </SettingCard>
  );
}

function FieldRow({
  field,
  value,
  options,
  onChange,
}: {
  field: ConfigField;
  value: unknown;
  options: ConfigSchema["options"];
  onChange: (v: unknown) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 p-5 md:grid-cols-[240px_1fr] md:gap-8">
      <div>
        <Label className="text-sm">{field.label}</Label>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          {field.name}
        </p>
        {field.help && (
          <p className="mt-1.5 text-xs text-muted-foreground">{field.help}</p>
        )}
      </div>
      <ConfigFieldControl
        field={field}
        value={value}
        options={options}
        onChange={onChange}
      />
    </div>
  );
}

function AdvancedCard({
  fields,
  local,
  options,
  set,
}: {
  fields: ConfigField[];
  local: ConfigMap;
  options: ConfigSchema["options"];
  set: (name: string, value: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  if (fields.length === 0) return null;
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="overflow-hidden rounded-lg border border-primary/15 bg-primary/[0.03]">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-3 p-4 text-left"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Settings2 className="h-4 w-4" />
            </span>
            <div className="flex-1">
              <span className="text-sm font-semibold">Advanced options</span>
              <p className="text-xs text-muted-foreground">
                Override engine defaults and fine-tune behavior.
              </p>
            </div>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                open && "rotate-180",
              )}
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="divide-y divide-border border-t border-border bg-card">
            {fields.map((f) => (
              <FieldRow
                key={f.name}
                field={f}
                value={local[f.name]}
                options={options}
                onChange={(v) => set(f.name, v)}
              />
            ))}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function StatusPills({
  isDefault,
  notes,
}: {
  isDefault: boolean;
  notes: string[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
      {isDefault ? (
        <Chip tone="green">
          <Check className="h-3 w-3" />
          Using recommended configuration
        </Chip>
      ) : (
        <Chip tone="violet">Custom configuration</Chip>
      )}
      <span className="text-muted-foreground">{notes.join("  •  ")}</span>
    </div>
  );
}

/* ---------- sections ---------- */

interface SectionProps {
  fields: ConfigField[];
  local: ConfigMap;
  options: ConfigSchema["options"];
  set: (name: string, value: unknown) => void;
}

function useSection(fields: ConfigField[], local: ConfigMap) {
  const field = (name: string) => fields.find((f) => f.name === name);
  const value = (name: string) => local[name];
  const rest = (handled: string[]) =>
    fields.filter((f) => !handled.includes(f.name));
  return { field, value, rest };
}

function OtherSettings({
  fields,
  local,
  options,
  set,
}: SectionProps) {
  if (fields.length === 0) return null;
  return (
    <Card>
      <CardContent className="divide-y divide-border p-0">
        {fields.map((f) => (
          <FieldRow
            key={f.name}
            field={f}
            value={local[f.name]}
            options={options}
            onChange={(v) => set(f.name, v)}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function PiiSection({ fields, local, options, set }: SectionProps) {
  const { field, value, rest } = useSection(fields, local);
  const action = field("pii_action");
  const threshold = field("pii_threshold");
  const entities = field("pii_entities");
  const advanced = [
    "pii_deny_list",
    "pii_allow_list",
    "pii_custom_regex",
    "pii_custom_context_keywords",
  ]
    .map(field)
    .filter((f): f is ConfigField => Boolean(f));
  const handled = [
    "pii_action",
    "pii_threshold",
    "pii_entities",
    ...advanced.map((f) => f.name),
  ];

  return (
    <>
      {action && (
        <SettingCard
          title="PII action"
          description="What to do when PII is found."
        >
          <ChoiceCards
            value={value("pii_action")}
            onChange={(v) => set("pii_action", v)}
            choices={[
              {
                value: "mask",
                title: "Mask",
                description: "Replace detected PII with placeholder tokens.",
                icon: EyeOff,
                badge:
                  action.default === "mask"
                    ? { text: "Recommended", tone: "violet" }
                    : undefined,
              },
              {
                value: "block",
                title: "Block",
                description: "Reject the request when PII is found.",
                icon: Ban,
                badge: { text: "Strictest", tone: "green" },
              },
              {
                value: "none",
                title: "Detect only",
                description: "Report entities and leave the text unchanged.",
                icon: ScanEye,
                badge: { text: "Observability", tone: "green" },
              },
            ]}
          />
        </SettingCard>
      )}

      {threshold && (
        <SettingCard
          title="Sensitivity"
          description={threshold.help}
          badge={
            <span className="text-[11px] text-muted-foreground">
              default {String(threshold.default)}
            </span>
          }
        >
          <ThresholdSlider
            field={threshold}
            value={
              typeof value("pii_threshold") === "number"
                ? (value("pii_threshold") as number)
                : Number(threshold.default)
            }
            onChange={(v) => set("pii_threshold", v)}
          />
        </SettingCard>
      )}

      {entities && (
        <SettingCard title="Entity types" description={entities.help}>
          <ConfigFieldControl
            field={entities}
            value={value("pii_entities")}
            options={options}
            onChange={(v) => set("pii_entities", v)}
          />
        </SettingCard>
      )}

      <AdvancedCard fields={advanced} local={local} options={options} set={set} />
      <OtherSettings
        fields={rest(handled)}
        local={local}
        options={options}
        set={set}
      />
    </>
  );
}

function ContentSection({ fields, local, options, set }: SectionProps) {
  const { field, value, rest } = useSection(fields, local);
  const cascade = field("cascade_mode");
  const categories = field("categories");

  return (
    <>
      {cascade && (
        <SettingCard
          title="Cascade mode"
          description="Choose the balance between coverage and latency."
        >
          <ChoiceCards
            columns={2}
            value={value("cascade_mode")}
            onChange={(v) => set("cascade_mode", v)}
            choices={[
              {
                value: "safety",
                title: "Safety",
                description: "Runs the full classifier cascade on every request.",
                icon: ShieldCheck,
                badge:
                  cascade.default === "safety"
                    ? { text: "Recommended", tone: "violet" }
                    : undefined,
              },
              {
                value: "speed",
                title: "Speed",
                description: "Short-circuits on the first confident verdict.",
                icon: Zap,
                badge: { text: "Lowest latency", tone: "green" },
              },
            ]}
          />
        </SettingCard>
      )}

      {categories && (
        <SettingCard title="Blocked categories" description={categories.help}>
          <ConfigFieldControl
            field={categories}
            value={value("categories")}
            options={options}
            onChange={(v) => set("categories", v)}
          />
        </SettingCard>
      )}

      <OtherSettings
        fields={rest(["cascade_mode", "categories"])}
        local={local}
        options={options}
        set={set}
      />
    </>
  );
}

function ScopeSection({ fields, local, options, set }: SectionProps) {
  const { field, value, rest } = useSection(fields, local);
  const width = field("scope_width");
  const topics = field("scope_topics");
  const examples = field("scope_examples");
  const threshold = field("scope_threshold");
  const alpha = field("scope_alpha");
  const topicList = Array.isArray(value("scope_topics"))
    ? (value("scope_topics") as string[])
    : [];

  return (
    <>
      {topicList.length === 0 && (
        <InfoBanner>
          Scope checking is off until at least one topic is added below.
        </InfoBanner>
      )}

      {width && (
        <SettingCard
          title="Scope width"
          description="How strictly requests must match your topics."
        >
          <ChoiceCards
            columns={4}
            value={value("scope_width")}
            onChange={(v) => set("scope_width", v)}
            choices={[
              {
                value: "narrow",
                title: "Narrow",
                description: "Only clearly on-topic queries pass.",
                icon: Crosshair,
                badge: { text: "Strictest", tone: "green" },
              },
              {
                value: "moderate",
                title: "Moderate",
                description: "Balanced matching around your topics.",
                icon: Scale,
                badge:
                  width.default === "moderate"
                    ? { text: "Recommended", tone: "violet" }
                    : undefined,
              },
              {
                value: "broad",
                title: "Broad",
                description: "Only clearly off-topic queries are blocked.",
                icon: Shield,
                badge: { text: "Most permissive", tone: "green" },
              },
              {
                value: "fitted",
                title: "Fitted",
                description: "Threshold learned from your examples via fit().",
                icon: Sparkles,
                badge: { text: "Data-driven", tone: "green" },
              },
            ]}
          />
        </SettingCard>
      )}

      {(topics || examples) && (
        <Card>
          <CardContent className="divide-y divide-border p-0">
            {topics && (
              <FieldRow
                field={topics}
                value={value("scope_topics")}
                options={options}
                onChange={(v) => set("scope_topics", v)}
              />
            )}
            {examples && (
              <FieldRow
                field={examples}
                value={value("scope_examples")}
                options={options}
                onChange={(v) => set("scope_examples", v)}
              />
            )}
          </CardContent>
        </Card>
      )}

      {threshold && (
        <AutoOrCustomCard
          title="Sensitivity"
          description="How strict GuardEx is when matching topics."
          autoTitle="Automatic"
          autoDescription="Derives the threshold from the scope width above."
          customDescription="Set the scope threshold manually."
          field={threshold}
          value={value("scope_threshold")}
          onChange={(v) => set("scope_threshold", v)}
        />
      )}

      <AdvancedCard
        fields={alpha ? [alpha] : []}
        local={local}
        options={options}
        set={set}
      />
      <OtherSettings
        fields={rest([
          "scope_width",
          "scope_topics",
          "scope_examples",
          "scope_threshold",
          "scope_alpha",
        ])}
        local={local}
        options={options}
        set={set}
      />
    </>
  );
}

function RoutesSection({ fields, local, options, set }: SectionProps) {
  const { field, value, rest } = useSection(fields, local);
  const routes = field("safety_routes");

  return (
    <>
      {routes && (
        <SettingCard title="Routes" description={routes.help}>
          <ConfigFieldControl
            field={routes}
            value={value("safety_routes")}
            options={options}
            onChange={(v) => set("safety_routes", v)}
          />
        </SettingCard>
      )}
      <OtherSettings
        fields={rest(["safety_routes"])}
        local={local}
        options={options}
        set={set}
      />
    </>
  );
}

function GroundingSection({ fields, local, options, set }: SectionProps) {
  const { field, value, rest } = useSection(fields, local);
  const mode = field("grounding_mode");
  const threshold = field("grounding_threshold");

  return (
    <>
      {mode && (
        <SettingCard
          title="Grounding strategy"
          description="Choose the balance between verification accuracy and latency."
        >
          <div className="space-y-3">
            <ChoiceCards
              value={value("grounding_mode")}
              onChange={(v) => set("grounding_mode", v)}
              choices={[
                {
                  value: "speed",
                  title: "Fast",
                  description: "Embedding similarity only, for minimum latency.",
                  icon: Zap,
                  badge: { text: "Lowest latency", tone: "green" },
                  meta: "~10 ms",
                },
                {
                  value: null,
                  title: "Auto",
                  description:
                    "Engine default: NLI verification when the model is loaded, embeddings otherwise.",
                  icon: Scale,
                  badge: { text: "Recommended", tone: "violet" },
                  meta: "adaptive",
                },
                {
                  value: "accuracy",
                  title: "Accurate",
                  description: "NLI verification for the highest accuracy.",
                  icon: ShieldCheck,
                  badge: { text: "Highest accuracy", tone: "green" },
                  meta: "~50–200 ms",
                },
              ]}
            />
            <InfoBanner>
              Accurate mode falls back to embedding similarity when the NLI
              model is not loaded.
            </InfoBanner>
          </div>
        </SettingCard>
      )}

      {threshold && (
        <AutoOrCustomCard
          title="Sensitivity"
          description="How strict GuardEx is when evaluating grounding."
          autoTitle="Automatic"
          autoDescription="Uses the engine default threshold."
          customDescription="Set the grounding threshold manually."
          field={threshold}
          value={value("grounding_threshold")}
          onChange={(v) => set("grounding_threshold", v)}
        />
      )}

      <OtherSettings
        fields={rest(["grounding_mode", "grounding_threshold"])}
        local={local}
        options={options}
        set={set}
      />
    </>
  );
}

const SECTION_BODY: Record<
  string,
  (props: SectionProps) => JSX.Element | null
> = {
  pii: PiiSection,
  content: ContentSection,
  scope: ScopeSection,
  routes: RoutesSection,
  grounding: GroundingSection,
};

/* ---------- summary pills ---------- */

function sectionNotes(key: string, local: ConfigMap): string[] {
  const list = (name: string) =>
    Array.isArray(local[name]) ? (local[name] as unknown[]) : [];
  switch (key) {
    case "pii": {
      const action = local["pii_action"];
      const label =
        action === "mask"
          ? "Masking detected PII"
          : action === "block"
            ? "Blocking on PII"
            : "Detect only";
      return [label, `${list("pii_entities").length} entity types`];
    }
    case "content": {
      const cascade =
        local["cascade_mode"] === "speed"
          ? "Speed short-circuit"
          : "Full safety cascade";
      const n = list("categories").length;
      return [cascade, n === 0 ? "Classifier default categories" : `${n} blocked categories`];
    }
    case "scope": {
      const n = list("scope_topics").length;
      const width = String(local["scope_width"] ?? "moderate");
      if (n === 0) return ["Scope checking off"];
      return [
        `${n} topic${n === 1 ? "" : "s"}`,
        `${width} width`,
        local["scope_threshold"] == null
          ? "Automatic threshold"
          : `Threshold ${Number(local["scope_threshold"]).toFixed(2)}`,
      ];
    }
    case "routes": {
      const n = list("safety_routes").length;
      return [n === 0 ? "No routes defined" : `${n} route${n === 1 ? "" : "s"}`];
    }
    case "grounding": {
      const mode = local["grounding_mode"];
      const label =
        mode === "speed"
          ? "Fast verification"
          : mode === "accuracy"
            ? "Accurate verification"
            : "Auto verification";
      return [
        label,
        local["grounding_threshold"] == null
          ? "Automatic sensitivity"
          : `Threshold ${Number(local["grounding_threshold"]).toFixed(2)}`,
      ];
    }
    default:
      return [];
  }
}

/* ---------- page ---------- */

export default function Config() {
  const queryClient = useQueryClient();
  const { data: schema } = useQuery({ queryKey: ["configSchema"], queryFn: getConfigSchema });
  const { data: remote } = useQuery({ queryKey: ["config"], queryFn: getConfig });

  const [local, setLocal] = useState<ConfigMap | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    if (remote?.config) setLocal(remote.config);
  }, [remote]);

  const groups = useMemo(() => {
    if (!schema) return [];
    return [...new Set(schema.fields.map((f) => f.group))];
  }, [schema]);

  useEffect(() => {
    if (!active && groups.length > 0) setActive(groups[0]);
  }, [groups, active]);

  const apply = useMutation({
    mutationFn: putConfig,
    onError: (err: Error) => toast.error(err.message),
  });

  const save = useMutation({
    mutationFn: saveConfig,
    onSuccess: (data) => toast.success(`Saved to ${data.path}`),
    onError: (err: Error) => toast.error(err.message),
  });

  const change = (name: string, value: unknown) => {
    setLocal((prev) => ({ ...(prev ?? {}), [name]: value }));
    clearTimeout(timers.current[name]);
    timers.current[name] = setTimeout(() => apply.mutate({ [name]: value }), 400);
  };

  if (!schema || !local || !active) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const fieldsOf = (group: string) => schema.fields.filter((f) => f.group === group);
  const isDefault = (group: string) =>
    fieldsOf(group).every((f) => same(local[f.name], f.default));

  const resetSection = (group: string) => {
    const patch = Object.fromEntries(fieldsOf(group).map((f) => [f.name, f.default]));
    setLocal((prev) => ({ ...(prev ?? {}), ...patch }));
    apply.mutate(patch, {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: ["config"] });
        toast.success("Reset to defaults");
      },
    });
  };

  const meta = SECTION_META[active] ?? {
    label: active,
    title: active,
    description: "",
    icon: Settings2,
  };
  const Body = SECTION_BODY[active] ?? OtherSettings;
  const navGroups = [
    ...NAV_GROUPS.map((g) => ({ ...g, keys: g.keys.filter((k) => groups.includes(k)) })),
    { label: "Other", keys: groups.filter((g) => !NAV_GROUPS.some((n) => n.keys.includes(g))) },
  ].filter((g) => g.keys.length > 0);

  return (
    <div className="flex gap-8 pb-14">
      <aside className="hidden w-52 shrink-0 md:block">
        <div className="sticky top-24 space-y-1">
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Configuration
          </p>
          {navGroups.map((g) => (
            <div key={g.label}>
              <p className="mt-4 px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {g.label}
              </p>
              {g.keys.map((key) => {
                const m = SECTION_META[key];
                const NavIcon = m?.icon ?? Settings2;
                const selected = key === active;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setActive(key)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                      selected
                        ? "bg-secondary font-medium text-secondary-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    <NavIcon className="h-4 w-4" />
                    {m?.label ?? key}
                    {!isDefault(key) && (
                      <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </aside>

      <div className="min-w-0 flex-1 space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-gradient-to-br from-primary/15 to-primary/5 text-primary">
              <meta.icon className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold">{meta.title}</h1>
              <p className="mt-1 max-w-xl text-sm text-muted-foreground">
                {meta.description}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 gap-2"
            onClick={() => resetSection(active)}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset to defaults
          </Button>
        </div>

        <StatusPills
          isDefault={isDefault(active)}
          notes={sectionNotes(active, local)}
        />

        <Body
          fields={fieldsOf(active)}
          local={local}
          options={schema.options}
          set={change}
        />

        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-background/95 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-3 px-8 py-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Info className="h-3.5 w-3.5" />
              Changes apply to the running server immediately. Requests that
              set a field explicitly still win.
            </span>
            <span className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    apply.isPending ? "bg-warning" : "bg-success",
                  )}
                />
                {apply.isPending ? "Applying…" : "Applied live"}
              </span>
              <Button
                size="sm"
                className="gap-2"
                onClick={() => save.mutate()}
              >
                <Save className="h-3.5 w-3.5" />
                Save to guardex.policy.yaml
              </Button>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
