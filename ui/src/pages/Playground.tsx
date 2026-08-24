import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2, Play, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { GateCard } from "@/components/GateCard";
import { gateLabel, namedGates } from "@/lib/gates";
import {
  getConfig,
  getConfigSchema,
  getSamples,
  putConfig,
  runPlayground,
  type ConfigMap,
  type GateName,
  type PlaygroundResult,
  type Sample,
} from "@/lib/api";

const GATE_ORDER: GateName[] = [
  "injection",
  "safety",
  "pii",
  "scope",
  "routes",
  "grounding",
];

const IDLE_GATES = GATE_ORDER.map((name) => ({
  name,
  status: "skipped" as const,
  summary: "",
  duration_ms: 0,
  detail: [],
  note: "",
}));

export default function Playground() {
  const queryClient = useQueryClient();
  const { data: schema } = useQuery({
    queryKey: ["configSchema"],
    queryFn: getConfigSchema,
  });
  const { data: remoteConfig } = useQuery({ queryKey: ["config"], queryFn: getConfig });
  const { data: sampleData } = useQuery({ queryKey: ["samples"], queryFn: getSamples });

  const [text, setText] = useState("");
  const [sources, setSources] = useState("");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [stage, setStage] = useState("input");
  const [config, setConfig] = useState<ConfigMap | null>(null);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonOpen, setJsonOpen] = useState(false);

  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const rerunTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({ text, sources, stage });
  latest.current = { text, sources, stage };

  useEffect(() => {
    if (remoteConfig?.config) setConfig(remoteConfig.config);
  }, [remoteConfig]);

  const samplesByGate = useMemo(() => {
    const map: Partial<Record<GateName, Sample>> = {};
    for (const s of sampleData?.samples ?? []) map[s.gate] = s;
    return map;
  }, [sampleData]);

  const run = async (override?: { text?: string; sources?: string }) => {
    const body = {
      text: override?.text ?? latest.current.text,
      sources: (override?.sources ?? latest.current.sources)
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      stage: latest.current.stage,
    };
    if (!body.text.trim()) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await runPlayground(body));
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
      void queryClient.invalidateQueries({ queryKey: ["logStats"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
      setResult(null);
    } finally {
      setRunning(false);
    }
  };

  const changeConfig = (name: string, value: unknown) => {
    setConfig((prev) => ({ ...(prev ?? {}), [name]: value }));
    clearTimeout(timers.current[name]);
    timers.current[name] = setTimeout(async () => {
      try {
        await putConfig({ [name]: value });
        void queryClient.invalidateQueries({ queryKey: ["config"] });
        if (rerunTimer.current) clearTimeout(rerunTimer.current);
        rerunTimer.current = setTimeout(() => {
          if (latest.current.text.trim()) void run();
        }, 120);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Config update failed");
      }
    }, 400);
  };

  const loadSample = async (gate: GateName) => {
    const s = samplesByGate[gate];
    if (!s) return;
    setText(s.text);
    const src = (s.sources ?? []).join("\n");
    setSources(src);
    if (s.sources?.length) setSourcesOpen(true);
    latest.current = { ...latest.current, text: s.text, sources: src };
    if (Object.keys(s.config).length) {
      setConfig((prev) => ({ ...(prev ?? {}), ...s.config }));
      try {
        await putConfig(s.config);
        void queryClient.invalidateQueries({ queryKey: ["config"] });
      } catch {
        // the run below still shows what the current config does
      }
    }
    void run({ text: s.text, sources: src });
  };

  const gates = result?.gates ?? IDLE_GATES;
  const flaggedNames =
    result?.gates.filter((g) => g.status === "flagged").map((g) => g.name) ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Playground</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            One input, every layer. Change a setting and it re-runs against the live
            server policy.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">Stage</Label>
          <Select value={stage} onValueChange={setStage}>
            <SelectTrigger className="h-8 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="input">Input</SelectItem>
              <SelectItem value="output">Output</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,30rem)] xl:items-start">
        <div className="min-w-0 space-y-5">
      <Card>
        <CardContent className="space-y-3 p-4">
          <Textarea
            placeholder="Paste anything a user might send, or a reply your model produced…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                void run();
              }
            }}
            className="min-h-[104px] resize-y border-0 bg-transparent p-0 text-[15px] shadow-none focus-visible:ring-0"
          />

          <Collapsible open={sourcesOpen} onOpenChange={setSourcesOpen}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                {sourcesOpen ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
                Reference sources
                <span className="text-muted-foreground/60">
                  (unlocks the grounding check)
                </span>
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Textarea
                placeholder={"One source per line.\nThe refund window is 30 days."}
                value={sources}
                onChange={(e) => setSources(e.target.value)}
                className="mt-2 min-h-[72px] resize-y font-mono text-xs"
              />
            </CollapsibleContent>
          </Collapsible>

          <div className="flex items-center justify-between border-t border-border pt-3">
            <span className="text-xs text-muted-foreground">
              {result ? (
                <>
                  {flaggedNames.length > 0 ? (
                    <span className="text-red-500">
                      Caught by {namedGates(flaggedNames)}
                    </span>
                  ) : (
                    <span className="text-primary">Nothing caught</span>
                  )}
                  <span className="ml-2 font-mono tabular-nums">
                    {result.total_ms.toFixed(0)}ms
                  </span>
                </>
              ) : (
                "Ctrl+Enter to run"
              )}
            </span>
            <Button
              size="sm"
              onClick={() => void run()}
              disabled={running || !text.trim()}
              className="gap-2"
            >
              {running ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {running ? "Screening…" : "Screen"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="space-y-2">
        {gates.map((g) => (
          <GateCard
            key={g.name}
            gate={g}
            schema={schema}
            config={config}
            onConfigChange={changeConfig}
            onSample={samplesByGate[g.name] ? () => void loadSample(g.name) : null}
            running={running}
          />
        ))}
      </div>

        </div>

        <aside
          className={cn(
            "xl:sticky xl:top-[76px]",
            result && jsonOpen
              ? "xl:h-[calc(100vh-6.5rem)]"
              : "xl:max-h-[calc(100vh-6.5rem)]",
          )}
        >
          <Card className="flex h-full flex-col overflow-hidden">
            <CardContent className="flex min-h-0 flex-1 flex-col gap-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Text your model receives
                </Label>
                {result && (
                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                    {result.total_ms.toFixed(0)}ms
                  </span>
                )}
              </div>

              {result ? (
                <div className="flex min-h-0 flex-1 flex-col gap-3">
                  <div className="max-h-56 shrink-0 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-mono text-sm">
                    {result.text}
                  </div>

                  {flaggedNames.length > 0 ? (
                    <div className="flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="text-muted-foreground">Caught by</span>
                      {flaggedNames.map((name) => (
                        <span
                          key={name}
                          className="rounded border border-red-500/25 bg-red-500/10 px-1.5 py-0.5 text-[11px] text-red-500"
                        >
                          {gateLabel(name)}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-primary">
                      Nothing caught. This would reach your model unchanged.
                    </p>
                  )}

                  <Collapsible
                    open={jsonOpen}
                    onOpenChange={setJsonOpen}
                    className={jsonOpen ? "flex min-h-0 flex-1 flex-col" : "shrink-0"}
                  >
                    <CollapsibleTrigger asChild>
                      <button
                        type="button"
                        className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {jsonOpen ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                        Full JSON response
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="mt-2 min-h-0 flex-1 overflow-hidden">
                      <div className="h-full overflow-auto rounded-md bg-muted p-3 font-mono text-xs">
                        <pre>{JSON.stringify(result, null, 2)}</pre>
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              ) : (
                <div className="flex flex-col items-center py-10 text-center">
                  <ShieldCheck className="mb-2 h-7 w-7 text-muted-foreground/30" />
                  <p className="text-xs text-muted-foreground">
                    Nothing screened yet. Type on the left, or hit{" "}
                    <strong>See it catch</strong> on any gate.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
