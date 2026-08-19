import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { ConfigField, ConfigSchema } from "@/lib/api";

interface Props {
  field: ConfigField;
  value: unknown;
  options: ConfigSchema["options"];
  onChange: (v: unknown) => void;
}

function ChipInput({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  };
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="outline" size="icon" onClick={add}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v) => (
            <Badge key={v} variant="secondary" className="gap-1 font-mono text-xs">
              {v}
              <button
                type="button"
                onClick={() => onChange(values.filter((x) => x !== v))}
                aria-label={`Remove ${v}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function MapEditor({
  entries,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
}: {
  entries: Array<[string, string]>;
  onChange: (e: Array<[string, string]>) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
}) {
  // A half-typed row cannot live in the config: it is keyed by label, and the
  // commit filter drops blank keys and blank values. So rows are held here and
  // only the complete ones are pushed up.
  const [rows, setRows] = useState<Array<[string, string]>>(entries);
  const incoming = JSON.stringify(entries);
  const committed = JSON.stringify(rows.filter(([k, v]) => k.trim() && v.trim()));

  useEffect(() => {
    if (incoming !== committed) setRows(entries);
    // Resync only when the config itself changed (reset, sample load), not on
    // every keystroke - which would wipe the row being typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incoming]);

  const update = (next: Array<[string, string]>) => {
    setRows(next);
    onChange(next);
  };

  return (
    <div className="space-y-2">
      {rows.map(([k, v], i) => (
        <div key={i} className="flex gap-2">
          <Input
            className="w-1/3 font-mono text-xs"
            value={k}
            placeholder={keyPlaceholder}
            onChange={(e) => {
              const next = [...rows];
              next[i] = [e.target.value, v];
              update(next);
            }}
          />
          <Input
            className="flex-1 font-mono text-xs"
            value={v}
            placeholder={valuePlaceholder}
            onChange={(e) => {
              const next = [...rows];
              next[i] = [k, e.target.value];
              update(next);
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => update(rows.filter((_, j) => j !== i))}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={() => setRows([...rows, ["", ""]])}
      >
        <Plus className="h-3.5 w-3.5" />
        Add
      </Button>
    </div>
  );
}

export function ConfigFieldControl({ field, value, options, onChange }: Props) {
  switch (field.type) {
    case "enum":
      return (
        <Select value={String(value ?? "")} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.choices ?? []).map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );

    case "float": {
      const n = typeof value === "number" ? value : 0;
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {field.min} – {field.max}
            </span>
            <span className="font-mono text-xs tabular-nums">{n.toFixed(2)}</span>
          </div>
          <Slider
            value={[n]}
            min={field.min ?? 0}
            max={field.max ?? 1}
            step={field.step ?? 0.05}
            onValueChange={([v]) => onChange(v)}
          />
        </div>
      );
    }

    case "enum_or_null": {
      const isAuto = value === null || value === undefined;
      return (
        <Select
          value={isAuto ? "__auto__" : String(value)}
          onValueChange={(v) => onChange(v === "__auto__" ? null : v)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__auto__">Engine default</SelectItem>
            {(field.choices ?? []).map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    case "route_list": {
      const routes = (Array.isArray(value) ? value : []) as Array<{
        name?: string;
        utterances?: string[];
        action?: string;
        threshold?: number;
      }>;
      const update = (i: number, patch: Record<string, unknown>) => {
        const next = routes.map((r, j) => (i === j ? { ...r, ...patch } : r));
        onChange(next);
      };
      return (
        <div className="space-y-2">
          {routes.map((r, i) => (
            <div key={i} className="space-y-2 rounded-md border border-border p-2.5">
              <div className="flex gap-2">
                <Input
                  className="h-8 flex-1 text-xs"
                  placeholder="Route name"
                  value={r.name ?? ""}
                  onChange={(e) => update(i, { name: e.target.value })}
                />
                <Select
                  value={r.action ?? "block"}
                  onValueChange={(v) => update(i, { action: v })}
                >
                  <SelectTrigger className="h-8 w-24 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="block">block</SelectItem>
                    <SelectItem value="flag">flag</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onChange(routes.filter((_, j) => j !== i))}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Input
                className="h-8 text-xs"
                placeholder="Example utterances, comma separated"
                value={(r.utterances ?? []).join(", ")}
                onChange={(e) =>
                  update(i, {
                    utterances: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
              />
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() =>
              onChange([
                ...routes,
                { name: "", utterances: [], action: "block", threshold: 0.35 },
              ])
            }
          >
            <Plus className="h-3.5 w-3.5" />
            Add route
          </Button>
        </div>
      );
    }

    case "float_or_null": {
      const isAuto = value === null || value === undefined;
      return (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Switch
              checked={isAuto}
              onCheckedChange={(on) => onChange(on ? null : (field.max ?? 1) / 2)}
            />
            <Label className="text-xs text-muted-foreground">
              Auto (derive from scope width)
            </Label>
          </div>
          {!isAuto && (
            <div className="space-y-2">
              <div className="flex justify-end">
                <span className="font-mono text-xs tabular-nums">
                  {Number(value).toFixed(2)}
                </span>
              </div>
              <Slider
                value={[Number(value)]}
                min={field.min ?? 0}
                max={field.max ?? 1}
                step={field.step ?? 0.05}
                onValueChange={([v]) => onChange(v)}
              />
            </div>
          )}
        </div>
      );
    }

    case "string_list": {
      const list = Array.isArray(value) ? (value as string[]) : [];

      if (field.options_source === "pii_entities") {
        const all = options.pii_entities;
        return (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {list.length} of {all.length} selected
              </span>
              <div className="flex gap-2">
                <button type="button" onClick={() => onChange(all)} className="hover:text-foreground">
                  All
                </button>
                <button type="button" onClick={() => onChange([])} className="hover:text-foreground">
                  None
                </button>
              </div>
            </div>
            <ScrollArea className="h-48 rounded-md border border-border p-3">
              <div className="grid grid-cols-2 gap-2">
                {all.map((entity) => (
                  <label key={entity} className="flex items-center gap-2 text-xs">
                    <Checkbox
                      checked={list.includes(entity)}
                      onCheckedChange={(on) =>
                        onChange(
                          on ? [...list, entity] : list.filter((x) => x !== entity),
                        )
                      }
                    />
                    <span className="font-mono">{entity}</span>
                  </label>
                ))}
              </div>
            </ScrollArea>
          </div>
        );
      }

      if (field.options_source === "categories") {
        const all = options.categories;
        return (
          <ScrollArea className="h-48 rounded-md border border-border p-3">
            <div className="space-y-2">
              {all.map((c) => (
                <label key={c.value} className="flex items-start gap-2 text-xs">
                  <Checkbox
                    checked={list.includes(c.value)}
                    onCheckedChange={(on) =>
                      onChange(on ? [...list, c.value] : list.filter((x) => x !== c.value))
                    }
                  />
                  <span>
                    <span className="font-mono">{c.value}</span>{" "}
                    <span className="text-muted-foreground">{c.label}</span>
                  </span>
                </label>
              ))}
            </div>
          </ScrollArea>
        );
      }

      return <ChipInput values={list} onChange={onChange} placeholder="Add and press Enter" />;
    }

    case "string_map": {
      const map = (value ?? {}) as Record<string, string>;
      return (
        <MapEditor
          entries={Object.entries(map)}
          keyPlaceholder="LABEL"
          valuePlaceholder="regular expression"
          onChange={(entries) =>
            // An empty pattern compiles and then matches at every position, so
            // a row is only committed once it has both a label and a pattern.
            onChange(
              Object.fromEntries(entries.filter(([k, v]) => k.trim() && v.trim())),
            )
          }
        />
      );
    }

    case "string_list_map": {
      const map = (value ?? {}) as Record<string, string[]>;
      return (
        <MapEditor
          entries={Object.entries(map).map(([k, v]) => [k, v.join(", ")])}
          keyPlaceholder="LABEL"
          valuePlaceholder="comma, separated, keywords"
          onChange={(entries) =>
            onChange(
              Object.fromEntries(
                entries
                  .filter(([k, v]) => k.trim() && v.trim())
                  .map(([k, v]) => [
                    k,
                    v.split(",").map((s) => s.trim()).filter(Boolean),
                  ]),
              ),
            )
          }
        />
      );
    }

    default:
      return null;
  }
}
