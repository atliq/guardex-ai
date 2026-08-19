import { useState } from "react";
import { ChevronDown, ChevronRight, Settings2, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ConfigFieldControl } from "@/components/ConfigFieldControl";
import { cn } from "@/lib/utils";
import { GATE_BLURB, GATE_LABELS } from "@/lib/gates";
import type {
  ConfigField,
  ConfigMap,
  ConfigSchema,
  GateResult,
  GateStatus,
} from "@/lib/api";

const STATUS: Record<GateStatus, { label: string; chip: string; dot: string }> = {
  flagged: {
    label: "Caught",
    chip: "border-red-500/25 bg-red-500/15 text-red-500",
    dot: "bg-red-500",
  },
  clean: {
    label: "Clean",
    chip: "border-primary/25 bg-primary/15 text-primary",
    dot: "bg-primary",
  },
  degraded: {
    label: "Degraded",
    chip: "border-amber-500/30 bg-amber-500/15 text-amber-600",
    dot: "bg-amber-500",
  },
  skipped: {
    label: "Off",
    chip: "border-border bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/40",
  },
  unavailable: {
    label: "No model",
    chip: "border-dashed border-muted-foreground/40 bg-transparent text-muted-foreground",
    dot: "bg-transparent ring-1 ring-muted-foreground/40",
  },
};

interface Props {
  gate: GateResult;
  schema: ConfigSchema | undefined;
  config: ConfigMap | null;
  onConfigChange: (name: string, value: unknown) => void;
  onSample: (() => void) | null;
  running: boolean;
}

export function GateCard({
  gate,
  schema,
  config,
  onConfigChange,
  onSample,
  running,
}: Props) {
  const [openSettings, setOpenSettings] = useState(false);
  const [openDetail, setOpenDetail] = useState(true);

  const status = STATUS[gate.status];
  const fieldNames = schema?.gate_groups?.[gate.name] ?? [];
  const fields: ConfigField[] = fieldNames
    .map((n) => schema?.fields.find((f) => f.name === n))
    .filter((f): f is ConfigField => Boolean(f));

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        gate.status === "flagged"
          ? "border-red-500/30 bg-red-500/[0.03]"
          : "border-border bg-card",
        running && "opacity-60",
      )}
    >
      <div className="flex items-start gap-3 px-4 py-3">
        <span className={cn("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", status.dot)} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{GATE_LABELS[gate.name]}</span>
            <Badge
              className={cn(
                "h-[18px] rounded px-1.5 text-[10px] font-medium uppercase tracking-wide",
                status.chip,
              )}
            >
              {status.label}
            </Badge>
            {gate.duration_ms > 0 && (
              <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                {gate.duration_ms.toFixed(1)}ms
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {gate.summary}
            {gate.note && <span className="italic"> ({gate.note})</span>}
          </p>
          {!gate.summary && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {GATE_BLURB[gate.name]}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {onSample && (
            <button
              type="button"
              onClick={onSample}
              title="Load an input that trips this gate"
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Sparkles className="h-3 w-3" />
              See it catch
            </button>
          )}
          {fields.length > 0 && (
            <button
              type="button"
              onClick={() => setOpenSettings((v) => !v)}
              aria-label="Gate settings"
              className={cn(
                "rounded-md p-1.5 transition-colors hover:bg-accent",
                openSettings ? "bg-accent text-foreground" : "text-muted-foreground",
              )}
            >
              <Settings2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {gate.detail.length > 0 && (
        <div className="border-t border-border/60 px-4 py-2.5">
          <button
            type="button"
            onClick={() => setOpenDetail((v) => !v)}
            className="mb-1.5 flex items-center gap-1 text-[11px] uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
          >
            {openDetail ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {gate.detail.length} finding{gate.detail.length === 1 ? "" : "s"}
          </button>
          {openDetail && (
            <div className="space-y-1">
              {gate.detail.map((d, i) => (
                <div
                  key={`${d.label}-${i}`}
                  className="flex flex-wrap items-center gap-2 rounded border border-border bg-muted/40 px-2.5 py-1.5 text-xs"
                >
                  <Badge variant="outline" className="h-[18px] px-1.5 font-mono text-[10px]">
                    {d.label}
                  </Badge>
                  {d.text && (
                    <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
                      "{d.text}"
                    </span>
                  )}
                  {d.method && (
                    <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {d.method}
                    </span>
                  )}
                  {d.severity && (
                    <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                      {d.severity}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {openSettings && fields.length > 0 && config && schema && (
        <>
          <Separator />
          <div className="space-y-4 bg-muted/30 px-4 py-4">
            {fields.map((f) => (
              <div key={f.name} className="grid gap-2 md:grid-cols-[180px_1fr] md:gap-5">
                <div>
                  <Label className="text-xs">{f.label}</Label>
                  <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    {f.name}
                  </p>
                </div>
                <ConfigFieldControl
                  field={f}
                  value={config[f.name]}
                  options={schema.options}
                  onChange={(v) => onConfigChange(f.name, v)}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
