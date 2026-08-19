import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfigFieldControl } from "@/components/ConfigFieldControl";
import {
  getConfig,
  getConfigSchema,
  putConfig,
  resetConfig,
  saveConfig,
  type ConfigMap,
} from "@/lib/api";

const GROUP_LABELS: Record<string, string> = {
  pii: "PII",
  content: "Content",
  scope: "Topic scope",
  routes: "Custom routes",
  grounding: "Grounding",
};

export default function Config() {
  const queryClient = useQueryClient();
  const { data: schema } = useQuery({ queryKey: ["configSchema"], queryFn: getConfigSchema });
  const { data: remote } = useQuery({ queryKey: ["config"], queryFn: getConfig });

  const [local, setLocal] = useState<ConfigMap | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    if (remote?.config) setLocal(remote.config);
  }, [remote]);

  const groups = useMemo(() => {
    if (!schema) return [];
    return [...new Set(schema.fields.map((f) => f.group))];
  }, [schema]);

  const apply = useMutation({
    mutationFn: putConfig,
    onError: (err: Error) => toast.error(err.message),
  });

  const reset = useMutation({
    mutationFn: resetConfig,
    onSuccess: (data) => {
      setLocal(data.config);
      void queryClient.invalidateQueries({ queryKey: ["config"] });
      toast.success("Reset to defaults");
    },
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

  if (!schema || !local) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h1 className="text-xl font-semibold">Config</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Applies to the running server immediately. Requests that set a field
          explicitly still win.
        </p>
      </div>

      <Tabs defaultValue={groups[0]}>
        <TabsList>
          {groups.map((g) => (
            <TabsTrigger key={g} value={g}>
              {GROUP_LABELS[g] ?? g}
            </TabsTrigger>
          ))}
        </TabsList>

        {groups.map((g) => (
          <TabsContent key={g} value={g} className="mt-4">
            <Card>
              <CardContent className="divide-y divide-border p-0">
                {schema.fields
                  .filter((f) => f.group === g)
                  .map((f) => (
                    <div
                      key={f.name}
                      className="grid grid-cols-1 gap-3 p-5 md:grid-cols-[240px_1fr] md:gap-8"
                    >
                      <div>
                        <Label className="text-sm">{f.label}</Label>
                        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                          {f.name}
                        </p>
                        {f.help && (
                          <p className="mt-1.5 text-xs text-muted-foreground">{f.help}</p>
                        )}
                      </div>
                      <ConfigFieldControl
                        field={f}
                        value={local[f.name]}
                        options={schema.options}
                        onChange={(v) => change(f.name, v)}
                      />
                    </div>
                  ))}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <div className="fixed inset-x-0 bottom-0 border-t border-border bg-background/95 backdrop-blur">
        <div className="flex w-full items-center gap-4 px-8 py-3">
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            {apply.isPending ? "Applying…" : "Applied live"}
          </span>
          <Separator orientation="vertical" className="h-5" />
          <div className="ml-auto flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => reset.mutate()}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset to defaults
            </Button>
            <Button size="sm" className="gap-2" onClick={() => save.mutate()}>
              <Save className="h-3.5 w-3.5" />
              Save to guardex.policy.yaml
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
