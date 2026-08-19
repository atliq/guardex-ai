import { Badge } from "@/components/ui/badge";
import type { PiiEntity } from "@/lib/api";

const METHOD_LABELS: Record<string, string> = {
  regex: "Regex",
  gliner: "AI",
  deny_list: "Deny",
};

export function EntityList({ entities }: { entities: PiiEntity[] }) {
  return (
    <div className="space-y-1.5">
      {entities.map((entity, i) => {
        const pct = entity.score * 100;
        const scoreColor =
          pct >= 80 ? "text-primary" : pct >= 50 ? "text-primary" : "text-red-500";
        const method = entity.method ? METHOD_LABELS[entity.method] ?? entity.method : "";
        return (
          <div
            key={`${entity.label}-${i}`}
            className="flex items-center justify-between rounded-md border border-border bg-muted/50 px-3 py-2 text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                {entity.label}
              </Badge>
              <span className="font-mono text-xs text-muted-foreground">
                "{entity.text}"
              </span>
              {method && (
                <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {method}
                </span>
              )}
              {entity.context_boost && (
                <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                  +ctx
                </span>
              )}
              {entity.corroborated && (
                <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                  verified
                </span>
              )}
            </div>
            <span className={`text-xs font-medium ${scoreColor}`}>{pct.toFixed(0)}%</span>
          </div>
        );
      })}
    </div>
  );
}
