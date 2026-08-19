import type { Diagnostic } from "@/lib/api";
import { cn } from "@/lib/utils";

export function GateTimeline({ diagnostics }: { diagnostics: Diagnostic[] }) {
  if (!diagnostics?.length) return null;
  const max = Math.max(1, ...diagnostics.map((d) => d.duration_ms ?? 0));
  return (
    <div className="space-y-1.5">
      {diagnostics.map((d) => (
        <div key={d.gate} className="flex items-center gap-3 text-xs">
          <span className="w-28 shrink-0 font-mono text-muted-foreground">{d.gate}</span>
          {d.ran ? (
            <>
              <div className="h-1.5 flex-1 rounded-full bg-muted">
                <div
                  className={cn(
                    "h-full rounded-full",
                    d.blocked ? "bg-red-500" : "bg-primary",
                  )}
                  style={{ width: `${((d.duration_ms ?? 0) / max) * 100}%` }}
                />
              </div>
              <span className="w-16 text-right font-mono tabular-nums text-muted-foreground">
                {(d.duration_ms ?? 0).toFixed(1)}ms
              </span>
            </>
          ) : (
            <span className="flex-1 italic text-muted-foreground/60">
              {d.skipped_reason}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
